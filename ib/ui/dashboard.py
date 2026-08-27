"""Cuadro de mando INGRESOS BOMBEOS.

Ocho pestañas: Resumen, Centrales, Revenue stack, Energía, Mercados, Previsión,
Nueva CHR y Calibración/QA.

Principios de la capa visual:
  * ninguna gráfica con dos ejes verticales;
  * la identidad nunca depende sólo del color: leyenda siempre presente y tabla
    de datos acompañando a cada bloque;
  * el color sigue a la entidad, no a su posición en el ranking;
  * observado, proxy, estimado y forecast se distinguen en la propia tabla.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html, no_update

from ..domain.aliases import AliasTable
from ..engines.forecast_engine import (ANCILLARY_SCENARIOS, StorageConfig,
                                       annual_projection, storage_from_inputs)
from ..pipeline import load_assets
from ..qa import quality_flags as qf
from ..repositories.processed_store import ProcessedStore
from .theme import DARK, GROUP_ORDER, LIGHT, MARKET_GROUPS, group_color, layout

TABLE_STYLE = dict(
    style_table={"overflowX": "auto", "maxHeight": "360px", "overflowY": "auto"},
    style_cell={"fontFamily": "Inter, Segoe UI, system-ui, sans-serif", "fontSize": "12px",
                "padding": "6px 10px", "border": "none"},
    style_header={"fontWeight": "600", "backgroundColor": "#f4f4f2", "border": "none",
                  "borderBottom": "1px solid #e6e5e1"},
    style_data={"borderBottom": "1px solid #f0efec"},
)


def empty_figure(theme: dict, title: str, message: str) -> go.Figure:
    """Figura vacía robusta. Nunca se usa px.scatter(x=[], y=[])."""
    fig = go.Figure()
    fig.update_layout(**layout(theme, title, height=280, showlegend=False))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=13, color=theme["text_muted"]))
    return fig


def _table(df: pd.DataFrame, max_rows: int = 400):
    d = df.head(max_rows).copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(2)
    return dash_table.DataTable(
        data=d.to_dict("records"),
        columns=[{"name": str(c), "id": str(c)} for c in d.columns],
        sort_action="native", filter_action="native", page_size=15, **TABLE_STYLE)


def _stat(label: str, value: str, note: str, theme: dict, status: str | None = None):
    color = theme.get(status, theme["text_primary"]) if status else theme["text_primary"]
    return html.Div([
        html.Div(label, style={"fontSize": "11px", "letterSpacing": ".04em",
                               "textTransform": "uppercase", "color": theme["text_muted"]}),
        html.Div(value, style={"fontSize": "26px", "fontWeight": 650, "color": color,
                               "lineHeight": "1.15", "margin": "4px 0 2px"}),
        html.Div(note, style={"fontSize": "11.5px", "color": theme["text_secondary"]}),
    ], style={"padding": "14px 16px", "background": theme["surface_2"],
              "borderRadius": "10px", "flex": "1 1 190px", "minWidth": "180px"})


def _storage_control_state(mode: str, volume_hm3, net_head_m,
                           turbine_efficiency) -> dict:
    """Devuelve un estado coherente para las dos formas de almacenamiento."""
    if mode == "reservoir":
        calculated_mwh = None
        try:
            storage = storage_from_inputs(
                volume_hm3=float(volume_hm3),
                net_head_m=float(net_head_m),
                turbine_efficiency=float(turbine_efficiency),
            )
            calculated_mwh = round(storage["usable_output_mwh"], 2)
        except (TypeError, ValueError):
            pass
        return {
            "mwh_disabled": True,
            "volume_disabled": False,
            "head_disabled": False,
            "calculated_mwh": calculated_mwh,
            "mwh_label": "Capacidad útil calculada (MWh)",
            "help": ("Introduce el volumen útil y el salto neto. La capacidad eléctrica útil "
                     "se calcula automáticamente aplicando la eficiencia de turbinado."),
        }
    return {
        "mwh_disabled": False,
        "volume_disabled": True,
        "head_disabled": True,
        "calculated_mwh": None,
        "mwh_label": "Capacidad útil (MWh)",
        "help": ("Introduce directamente los MWh eléctricos útiles. El volumen de la balsa "
                 "y el salto neto quedan desactivados."),
    }


def add_group(detail: pd.DataFrame) -> pd.DataFrame:
    d = detail.copy()
    d["grupo"] = d["market"].map(MARKET_GROUPS).fillna("Otros")
    d["month"] = pd.to_datetime(d["datetime"]).dt.to_period("M").dt.to_timestamp()
    return d


def revenue_stack_figure(detail: pd.DataFrame, theme: dict, by: str = "asset") -> go.Figure:
    d = add_group(detail)
    if d.empty:
        return empty_figure(theme, "Revenue stack", "Sin datos para la seleccion")
    g = d.groupby([by, "grupo"], as_index=False)["revenue_incremental"].sum()
    order = (g.groupby(by)["revenue_incremental"].sum().sort_values(ascending=False).index.tolist())
    colors = group_color(theme)
    fig = go.Figure()
    for grp in GROUP_ORDER:
        sub = g[g["grupo"] == grp]
        if sub.empty:
            continue
        s = sub.set_index(by).reindex(order)["revenue_incremental"]
        fig.add_bar(x=order, y=s.to_numpy(), name=grp,
                    marker=dict(color=colors[grp],
                                line=dict(color=theme["surface"], width=2)),
                    hovertemplate="%{x}<br>" + grp + ": %{y:,.0f} EUR<extra></extra>")
    fig.update_layout(**layout(theme, "Revenue stack por mercado (EUR)", height=430))
    fig.update_layout(barmode="relative", hovermode="closest")
    fig.update_yaxes(tickformat=",.0f")
    return fig


def monthly_stack_figure(detail: pd.DataFrame, theme: dict) -> go.Figure:
    d = add_group(detail)
    if d.empty:
        return empty_figure(theme, "Evolucion mensual", "Sin datos")
    g = d.groupby(["month", "grupo"], as_index=False)["revenue_incremental"].sum()
    colors = group_color(theme)
    fig = go.Figure()
    for grp in GROUP_ORDER:
        sub = g[g["grupo"] == grp].sort_values("month")
        if sub.empty:
            continue
        fig.add_bar(x=sub["month"], y=sub["revenue_incremental"], name=grp,
                    width=18 * 24 * 3600 * 1000,   # ancho fijo: un mes suelto no ocupa el lienzo
                    marker=dict(color=colors[grp], line=dict(color=theme["surface"], width=2)),
                    hovertemplate=grp + ": %{y:,.0f} EUR<extra></extra>")
    fig.update_layout(**layout(theme, "Ingresos mensuales por mercado (EUR)", height=380))
    fig.update_layout(barmode="relative")
    fig.update_yaxes(tickformat=",.0f")
    return fig


def captured_price_figure(cp: pd.DataFrame, theme: dict) -> go.Figure:
    if cp.empty:
        return empty_figure(theme, "Precios capturados", "Sin datos")
    d = cp.pivot_table(index="asset", columns="role", values="precio_capturado")
    d = d.sort_values(d.columns[0], ascending=True)
    fig = go.Figure()
    names = {"generation": "Precio capturado generacion", "pumping": "Coste capturado bombeo"}
    for i, role in enumerate([c for c in ["generation", "pumping"] if c in d.columns]):
        fig.add_bar(y=d.index, x=d[role], name=names[role], orientation="h",
                    marker=dict(color=theme["series"][i],
                                line=dict(color=theme["surface"], width=2)),
                    text=[f"{v:,.1f}" for v in d[role]], textposition="outside",
                    textfont=dict(size=11, color=theme["text_secondary"]),
                    hovertemplate="%{y}: %{x:,.2f} EUR/MWh<extra></extra>")
    fig.update_layout(**layout(theme, "Precio capturado por central (EUR/MWh)", height=420))
    fig.update_layout(barmode="group", hovermode="closest")
    return fig


def coverage_figure(cov: pd.DataFrame, theme: dict) -> go.Figure:
    if cov.empty:
        return empty_figure(theme, "Cobertura de precio", "Sin datos")
    d = cov.sort_values("cobertura_precio_pct")
    color = [theme["good"] if v >= 95 else theme["warning"] if v >= 50 else theme["critical"]
             for v in d["cobertura_precio_pct"].fillna(0)]
    fig = go.Figure()
    fig.add_bar(y=d["market"], x=d["cobertura_precio_pct"].fillna(0), orientation="h",
                marker=dict(color=color, line=dict(color=theme["surface"], width=2)),
                text=[f"{v:,.1f}%" for v in d["cobertura_precio_pct"].fillna(0)],
                textposition="outside", textfont=dict(size=11, color=theme["text_secondary"]),
                hovertemplate="%{y}: %{x:.1f}%<extra></extra>", showlegend=False)
    fig.update_layout(**layout(theme, "Cobertura de precio por mercado (%)", height=380,
                               showlegend=False))
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(range=[0, 112])
    return fig


def price_series_figure(pmd: pd.DataFrame, theme: dict) -> go.Figure:
    if pmd is None or pmd.empty:
        return empty_figure(theme, "Precio del mercado diario", "Sin serie de precios")
    d = pmd.copy()
    d["ts"] = pd.to_datetime(d["day"]) + pd.to_timedelta((d["qh"] - 1) * 15, unit="m")
    d = d.sort_values("ts")
    fig = go.Figure()
    fig.add_scatter(x=d["ts"], y=d["pmd"], mode="lines", name="PMD",
                    line=dict(color=theme["series"][0], width=2),
                    hovertemplate="%{x|%d/%m %H:%M}<br>PMD %{y:,.2f} EUR/MWh<extra></extra>")
    fig.update_layout(**layout(theme, "Precio marginal del mercado diario (EUR/MWh)", height=340))
    return fig


def forecast_figure(rows: pd.DataFrame, theme: dict) -> go.Figure:
    """Evolución anual con el rango Low–High y la trayectoria Base."""
    if rows.empty:
        return empty_figure(theme, "Ingreso neto prospectivo", "Configura la CHR y pulsa calcular")
    pivot = rows.pivot(index="anio", columns="escenario", values="eur_mw_anio").sort_index()
    fig = go.Figure()
    if {"Low", "High"}.issubset(pivot.columns):
        fig.add_scatter(x=pivot.index, y=pivot["High"], mode="lines", name="Escenario alto",
                        line=dict(color=theme["series"][2], width=1, dash="dot"),
                        hovertemplate="Alto %{y:,.0f} €/MW·año<extra></extra>")
        fig.add_scatter(x=pivot.index, y=pivot["Low"], mode="lines", name="Escenario bajo",
                        line=dict(color=theme["series"][0], width=1, dash="dot"),
                        fill="tonexty", fillcolor="rgba(42,120,214,0.13)",
                        hovertemplate="Bajo %{y:,.0f} €/MW·año<extra></extra>")
    if "Base" in pivot.columns:
        fig.add_scatter(x=pivot.index, y=pivot["Base"], mode="lines+markers", name="Escenario base",
                        line=dict(color=theme["series"][1], width=3), marker=dict(size=7),
                        hovertemplate="Base %{y:,.0f} €/MW·año<extra></extra>")
    fig.update_layout(**layout(theme, "Ingreso neto prospectivo (€/MW·año)", height=410))
    fig.update_yaxes(tickformat=",.0f", zeroline=True,
                     zerolinecolor=theme["text_muted"], zerolinewidth=1)
    fig.update_xaxes(dtick=1)
    return fig


def forecast_stack_figure(rows: pd.DataFrame, theme: dict, year: int) -> go.Figure:
    """Puente de componentes para comparar los tres escenarios en un año."""
    d = rows[rows["anio"] == year].copy()
    if d.empty:
        return empty_figure(theme, "Componentes del forecast", "Sin resultados")
    fig = go.Figure()
    components = [
        ("Arbitraje", "arbitraje_eur", theme["series"][0], 1.0),
        ("Servicios de ajuste", "ssaa_eur", theme["series"][1], 1.0),
        ("OPEX variable", "opex_variable_eur", theme["series"][2], -1.0),
        ("OPEX fijo", "opex_fijo_eur", theme["text_muted"], -1.0),
    ]
    order = ["Low", "Base", "High"]
    for label, column, color, sign in components:
        values = d.set_index("escenario").reindex(order)[column].fillna(0) * sign / 1_000_000.0
        fig.add_bar(x=order, y=values, name=label,
                    marker=dict(color=color, line=dict(color=theme["surface"], width=1.5)),
                    hovertemplate=label + ": %{y:,.2f} M€<extra></extra>")
    fig.update_layout(**layout(theme, f"Componentes del ingreso en {year} (M€)", height=390))
    fig.update_layout(barmode="relative")
    fig.update_yaxes(tickformat=",.1f", zeroline=True,
                     zerolinecolor=theme["text_muted"], zerolinewidth=1)
    return fig


def build_app(root: Path, assets_path: Path) -> Dash:
    store = ProcessedStore(root)
    assets = load_assets(assets_path)
    aliases = AliasTable.from_assets(assets)
    detail = store.read("revenue_detail")
    rec = store.read("volume_reconciliation")
    sign = store.read("native_sign_check")
    calibration_path = assets_path.parent / "calibration_summary.csv"
    calibration = (pd.read_csv(calibration_path) if calibration_path.exists()
                   else pd.DataFrame())
    theme = LIGHT

    if not detail.empty:
        detail["datetime"] = pd.to_datetime(detail["datetime"])
        detail["revenue_incremental"] = pd.to_numeric(detail["revenue_incremental"], errors="coerce")
        detail["quantity"] = pd.to_numeric(detail["quantity"], errors="coerce")

    app = Dash(__name__, title="INGRESOS BOMBEOS")
    asset_options = [{"label": a, "value": a} for a in sorted(assets["asset"])]
    date_min = detail["datetime"].min() if not detail.empty else pd.Timestamp("2023-01-01")
    date_max = detail["datetime"].max() if not detail.empty else pd.Timestamp("2023-01-31")
    calendar_min = min(pd.Timestamp(date_min).normalize(), pd.Timestamp("2000-01-01"))
    calendar_max = max(pd.Timestamp(date_max).normalize(), pd.Timestamp.today().normalize())

    filters = html.Div([
        html.Div([html.Label("Centrales", style={"fontSize": "11px", "color": theme["text_muted"]}),
                  dcc.Dropdown(id="f-assets", options=asset_options,
                               value=[a["value"] for a in asset_options], multi=True)],
                 style={"flex": "3 1 320px"}),
        html.Div([html.Label("Desde", style={"fontSize": "11px", "color": theme["text_muted"]}),
                  dcc.DatePickerSingle(id="f-start", date=date_min,
                                       min_date_allowed=calendar_min,
                                       max_date_allowed=calendar_max,
                                       display_format="DD/MM/YYYY")],
                 style={"flex": "1 1 160px", "minWidth": "160px"}),
        html.Div([html.Label("Hasta", style={"fontSize": "11px", "color": theme["text_muted"]}),
                  dcc.DatePickerSingle(id="f-end", date=date_max,
                                       min_date_allowed=calendar_min,
                                       max_date_allowed=calendar_max,
                                       display_format="DD/MM/YYYY")],
                 style={"flex": "1 1 160px", "minWidth": "160px"}),
        html.Div([html.Label("Metrica", style={"fontSize": "11px", "color": theme["text_muted"]}),
                  dcc.Dropdown(id="f-metric", clearable=False, value="EUR",
                               options=[{"label": "Euros", "value": "EUR"},
                                        {"label": "EUR/MW", "value": "EUR_MW"},
                                        {"label": "EUR/MW-año", "value": "EUR_MW_YEAR"}])],
                 style={"flex": "1 1 190px"}),
    ], style={"display": "flex", "gap": "14px", "alignItems": "flex-end",
              "padding": "12px 18px", "background": theme["surface_2"],
              "borderRadius": "10px", "marginBottom": "14px", "flexWrap": "wrap"})

    app.layout = html.Div([
        html.Div([
            html.H1("INGRESOS BOMBEOS", style={"fontSize": "19px", "margin": 0,
                                               "letterSpacing": ".01em"}),
            html.Div("Ingresos observados de bombeos españoles y simulación técnico-económica "
                     "de futuros proyectos con datos públicos de OMIE y REE / e·sios",
                     style={"fontSize": "12.5px", "color": theme["text_secondary"],
                            "marginTop": "3px"}),
            html.Div(f"Datos cargados: {pd.Timestamp(date_min):%d/%m/%Y} – {pd.Timestamp(date_max):%d/%m/%Y}",
                     style={"fontSize": "11px", "color": theme["text_muted"],
                            "marginTop": "5px"}),
        ], style={"padding": "16px 18px 10px"}),
        filters,
        dcc.Tabs(id="tabs", value="resumen", children=[
            dcc.Tab(label="Resumen", value="resumen"),
            dcc.Tab(label="Centrales", value="centrales"),
            dcc.Tab(label="Revenue stack", value="stack"),
            dcc.Tab(label="Energía", value="energia"),
            dcc.Tab(label="Mercados", value="mercados"),
            dcc.Tab(label="Previsión", value="forecast"),
            dcc.Tab(label="Nueva CHR", value="nueva"),
            dcc.Tab(label="Calibración / QA", value="qa"),
        ]),
        html.Div(id="tab-content", style={"padding": "16px 18px 40px"}),
    ], style={"fontFamily": "Inter, Segoe UI, system-ui, sans-serif",
              "background": theme["surface"], "color": theme["text_primary"],
              "minHeight": "100vh"})

    def _filtered(sel_assets, start, end):
        if detail.empty:
            return detail
        d = detail
        if sel_assets:
            d = d[d["asset"].isin(sel_assets)]
        if start:
            d = d[d["datetime"] >= pd.Timestamp(start)]
        if end:
            d = d[d["datetime"] < pd.Timestamp(end) + pd.Timedelta(days=1)]
        return d

    def _scale(d: pd.DataFrame, metric: str) -> pd.DataFrame:
        if metric == "EUR" or d.empty:
            return d
        mw = assets.set_index("asset")["mw_reference"]
        out = d.copy()
        out["revenue_incremental"] = out["revenue_incremental"] / out["asset"].map(mw)
        if metric == "EUR_MW_YEAR" and not out.empty:
            days = max((out["datetime"].max() - out["datetime"].min()).days + 1, 1)
            out["revenue_incremental"] *= 365.25 / days
        return out

    @app.callback(Output("tab-content", "children"),
                  Input("tabs", "value"), Input("f-assets", "value"),
                  Input("f-start", "date"), Input("f-end", "date"),
                  Input("f-metric", "value"))
    def render(tab, sel_assets, start, end, metric):
        d = _filtered(sel_assets, start, end)
        ds = _scale(d, metric)
        unit = {"EUR": "EUR", "EUR_MW": "EUR/MW", "EUR_MW_YEAR": "EUR/MW-año"}[metric]

        if d.empty:
            return html.Div([
                html.P("No hay datos calculados todavia. Ejecuta la ingesta y el calculo:",
                       style={"marginBottom": "8px"}),
                html.Pre("python cli.py ingest --start 2023-01-01 --end 2023-01-31\n"
                         "python cli.py build  --start 2023-01-01 --end 2023-01-31",
                         style={"background": theme["surface_2"], "padding": "12px",
                                "borderRadius": "8px", "fontSize": "12px"}),
            ])

        energia = d[d["market"] != "AFRR_BANDA"]
        total = ds["revenue_incremental"].sum()
        obs = 100.0 * (d["data_class"] == "OBSERVADO").sum() / len(d)
        est = d.loc[d["data_class"] == "ESTIMADO", "revenue_incremental"].sum()

        if tab == "resumen":
            gen = energia[energia["up"].map(lambda u: aliases.role_of(u)) == "generation"]
            bom = energia[energia["up"].map(lambda u: aliases.role_of(u)) == "pumping"]
            p48 = d[d["market"] == "DA"]
            vg = p48[p48["up"].map(lambda u: aliases.role_of(u)) == "generation"]["quantity"].sum()
            vb = p48[p48["up"].map(lambda u: aliases.role_of(u)) == "pumping"]["quantity"].sum()
            pg = gen["revenue_incremental"].sum() / vg if vg else np.nan
            pb = -bom["revenue_incremental"].sum() / -vb if vb else np.nan
            return html.Div([
                html.Div([
                    _stat("Ingreso total", f"{total:,.0f} {unit}",
                          f"{d['asset'].nunique()} centrales", theme),
                    _stat("Precio capturado generacion", f"{pg:,.1f} EUR/MWh",
                          f"{vg:,.0f} MWh P48", theme),
                    _stat("Coste capturado bombeo", f"{pb:,.1f} EUR/MWh",
                          f"{abs(vb):,.0f} MWh P48", theme),
                    _stat("Dato observado", f"{obs:,.0f} %",
                          f"estimado {est:,.0f} EUR", theme,
                          "good" if obs > 90 else "warning"),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                          "marginBottom": "18px"}),
                dcc.Graph(figure=revenue_stack_figure(ds, theme), config={"displayModeBar": False}),
                dcc.Graph(figure=monthly_stack_figure(ds, theme), config={"displayModeBar": False}),
                html.H3("Tabla de datos", style={"fontSize": "13px", "marginTop": "18px"}),
                _table(add_group(ds).groupby(["asset", "grupo"], as_index=False)
                       ["revenue_incremental"].sum().rename(columns={"revenue_incremental": unit})),
            ])

        if tab == "centrales":
            from ..pipeline import captured_prices
            cp = captured_prices(d, aliases)
            cols = [c for c in ["asset", "operator", "estado_proyecto", "comunidad_autonoma",
                                "mw_reference", "band_mw_reference", "up_generation",
                                "up_pumping", "participante_mercado"] if c in assets.columns]
            return html.Div([
                dcc.Graph(figure=captured_price_figure(cp, theme), config={"displayModeBar": False}),
                html.H3("Catalogo de centrales", style={"fontSize": "13px", "marginTop": "10px"}),
                _table(assets[cols]),
                html.H3("Precios capturados", style={"fontSize": "13px", "marginTop": "16px"}),
                _table(cp),
            ])

        if tab == "stack":
            g = add_group(ds)
            return html.Div([
                dcc.Graph(figure=revenue_stack_figure(ds, theme), config={"displayModeBar": False}),
                dcc.Graph(figure=monthly_stack_figure(ds, theme), config={"displayModeBar": False}),
                html.H3("Detalle por mercado", style={"fontSize": "13px", "marginTop": "14px"}),
                _table(g.groupby(["asset", "market"], as_index=False).agg(
                    cantidad=("quantity", "sum"), bruto=("revenue_gross", "sum"),
                    incremental=("revenue_incremental", "sum"))),
            ])

        if tab == "energia":
            p48 = d[d["market"] == "DA"].copy()
            p48["role"] = p48["up"].map(lambda u: aliases.role_of(u))
            piv = p48.groupby(["asset", "role"], as_index=False)["quantity"].sum()
            fig = go.Figure()
            for i, role in enumerate(["generation", "pumping"]):
                sub = piv[piv["role"] == role]
                fig.add_bar(x=sub["asset"], y=sub["quantity"],
                            name="Generacion" if role == "generation" else "Bombeo",
                            marker=dict(color=theme["series"][i],
                                        line=dict(color=theme["surface"], width=2)),
                            hovertemplate="%{x}: %{y:,.0f} MWh<extra></extra>")
            fig.update_layout(**layout(theme, "Energia P48 por central (MWh)", height=400))
            fig.update_layout(barmode="relative", hovermode="closest")
            ratio = piv.pivot(index="asset", columns="role", values="quantity")
            if {"generation", "pumping"}.issubset(ratio.columns):
                ratio["ratio_gen_bombeo"] = ratio["generation"] / ratio["pumping"].abs()
            return html.Div([
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
                html.H3("Volumenes y ratio de ciclo", style={"fontSize": "13px"}),
                _table(ratio.reset_index()),
            ])

        if tab == "mercados":
            pmd = store.read("pmd")
            return html.Div([
                dcc.Graph(figure=price_series_figure(pmd, theme), config={"displayModeBar": False}),
                html.H3("Precio medio por mercado y sentido", style={"fontSize": "13px"}),
                _table(d.dropna(subset=["price"]).groupby(["market"], as_index=False).agg(
                    precio_medio=("price", "mean"), precio_min=("price", "min"),
                    precio_max=("price", "max"), filas=("price", "size"))),
            ])

        if tab == "forecast":
            return html.Div([
                html.Div([
                    html.H2("Simulador de un bombeo futuro", style={"fontSize": "17px", "margin": "0 0 5px"}),
                    html.Div("Combina un despacho óptimo sobre precios históricos con escenarios explícitos. "
                             "Los resultados son previsiones, no ingresos observados ni una oferta de mercado.",
                             style={"fontSize": "12.5px", "color": theme["text_secondary"]}),
                ], style={"marginBottom": "15px"}),
                html.Div([
                    html.Div([html.Label("Potencia turbinado (MW)"),
                              dcc.Input(id="fc-pt", type="number", value=500, style={"width": "100%"})],
                             style={"flex": "1 1 150px"}),
                    html.Div([html.Label("Potencia bombeo (MW)"),
                              dcc.Input(id="fc-pb", type="number", value=500, style={"width": "100%"})],
                             style={"flex": "1 1 150px"}),
                    html.Div([html.Label("Definir almacenamiento por"),
                              dcc.Dropdown(id="fc-energy-mode", value="mwh", clearable=False,
                                           options=[{"label": "MWh eléctricos útiles", "value": "mwh"},
                                                    {"label": "Balsa y salto", "value": "reservoir"}])],
                             style={"flex": "1 1 210px"}),
                    html.Div([html.Label("Capacidad útil (MWh)", id="fc-e-label"),
                              dcc.Input(id="fc-e", type="number", value=4000, min=1,
                                        style={"width": "100%"})], style={"flex": "1 1 170px"}),
                    html.Div([html.Label("Volumen útil (hm³)"),
                              dcc.Input(id="fc-volume", type="number", value=5, min=0.001,
                                        disabled=True, style={"width": "100%"})],
                             style={"flex": "1 1 160px"}),
                    html.Div([html.Label("Salto neto (m)"),
                              dcc.Input(id="fc-head", type="number", value=350, min=1,
                                        disabled=True, style={"width": "100%"})],
                             style={"flex": "1 1 150px"}),
                ], style={"display": "flex", "gap": "12px", "alignItems": "flex-end",
                          "flexWrap": "wrap", "padding": "14px", "background": theme["surface_2"],
                          "borderRadius": "10px", "marginBottom": "12px"}),
                html.Div("Introduce directamente los MWh eléctricos útiles. El volumen de la balsa "
                         "y el salto neto quedan desactivados.", id="fc-storage-help",
                         style={"fontSize": "11.5px", "color": theme["text_muted"],
                                "margin": "-4px 2px 12px"}),
                html.Details([
                    html.Summary("Supuestos técnicos y económicos", style={"cursor": "pointer", "fontWeight": 600}),
                    html.Div([
                    html.Div([html.Label("Eficiencia turbinado"),
                              dcc.Input(id="fc-eff-t", type="number", value=0.90, step=0.01,
                                        min=0.1, max=1, style={"width": "100%"})],
                             style={"flex": "1 1 150px"}),
                    html.Div([html.Label("Eficiencia bombeo"),
                              dcc.Input(id="fc-eff-p", type="number", value=0.87, step=0.01,
                                        min=0.1, max=1, style={"width": "100%"})],
                             style={"flex": "1 1 150px"}),
                    html.Div([html.Label("Disponibilidad (%)"),
                              dcc.Input(id="fc-availability", type="number", value=95, step=1,
                                        min=0, max=100, style={"width": "100%"})],
                             style={"flex": "1 1 150px"}),
                    html.Div([html.Label("Máx. ciclos/día"),
                              dcc.Input(id="fc-cycles", type="number", value=1, step=0.1,
                                        min=0.1, style={"width": "100%"})],
                             style={"flex": "1 1 150px"}),
                    html.Div([html.Label("OPEX variable (€/MWh movido)"),
                              dcc.Input(id="fc-var-opex", type="number", value=1.5, step=0.1,
                                        min=0, style={"width": "100%"})],
                             style={"flex": "1 1 190px"}),
                    html.Div([html.Label("OPEX fijo (€/kW·año)"),
                              dcc.Input(id="fc-fixed-opex", type="number", value=12, step=0.5,
                                        min=0, style={"width": "100%"})],
                             style={"flex": "1 1 180px"}),
                    html.Div([html.Label("Captura de servicios de ajuste"),
                              dcc.Dropdown(id="fc-ssaa", value="Central", clearable=False,
                                           options=[{"label": k, "value": k}
                                                    for k in ANCILLARY_SCENARIOS])],
                             style={"flex": "1 1 210px"}),
                    html.Div([html.Label("Crecimiento arbitraje (%/año)"),
                              dcc.Input(id="fc-arb-growth", type="number", value=0, step=0.5,
                                        style={"width": "100%"})], style={"flex": "1 1 185px"}),
                    html.Div([html.Label("Crecimiento SSAA (%/año)"),
                              dcc.Input(id="fc-ssaa-growth", type="number", value=0, step=0.5,
                                        style={"width": "100%"})], style={"flex": "1 1 180px"}),
                    html.Div([html.Label("Primer año"),
                              dcc.Input(id="fc-start-year", type="number", value=2027, step=1,
                                        style={"width": "100%"})], style={"flex": "1 1 120px"}),
                    html.Div([html.Label("Último año"),
                              dcc.Input(id="fc-end-year", type="number", value=2040, step=1,
                                        style={"width": "100%"})], style={"flex": "1 1 120px"}),
                    ], style={"display": "flex", "gap": "12px", "alignItems": "flex-end",
                              "flexWrap": "wrap", "marginTop": "14px"}),
                ], style={"padding": "14px", "border": f"1px solid {theme['grid']}",
                          "borderRadius": "10px", "marginBottom": "14px"}),
                html.Div([
                    html.Button("Calcular", id="fc-run", n_clicks=0,
                                style={"padding": "10px 22px", "borderRadius": "8px",
                                       "border": "none", "background": theme["series"][0],
                                       "color": "#fff", "cursor": "pointer"}),
                    html.Div("El periodo histórico seleccionado arriba se usa como backtest.",
                             style={"fontSize": "11.5px", "color": theme["text_muted"]}),
                ], style={"display": "flex", "gap": "12px", "alignItems": "center",
                          "marginBottom": "16px"}),
                html.Div(id="fc-output"),
            ])

        if tab == "nueva":
            template_cols = [c for c in assets.columns]
            return html.Div([
                html.P("Una CHR nueva se da de alta por configuracion, sin tocar codigo: "
                       "anade una fila a config/assets.csv o a config/future_chr_template.csv "
                       "con estado_proyecto distinto de operacion.",
                       style={"fontSize": "13px"}),
                html.P("Los campos sin dato publico verificado deben quedar como UNKNOWN. "
                       "El motor nunca inventa un parametro tecnico.",
                       style={"fontSize": "13px", "color": theme["text_secondary"]}),
                html.H3("Campos disponibles", style={"fontSize": "13px", "marginTop": "12px"}),
                _table(pd.DataFrame({"campo": template_cols})),
            ])

        if tab == "qa":
            cov = qf.coverage(d)
            mix = qf.data_class_mix(d)
            items = [
                *([html.H3("Calibraciones externas congeladas",
                           style={"fontSize": "13px", "marginTop": "0"}),
                   _table(calibration)] if not calibration.empty else []),
                dcc.Graph(figure=coverage_figure(cov, theme), config={"displayModeBar": False}),
                html.H3("Cobertura por mercado", style={"fontSize": "13px"}),
                _table(cov),
                html.H3("Observado frente a estimado (EUR)", style={"fontSize": "13px",
                                                                   "marginTop": "16px"}),
                _table(mix),
                html.H3("Banderas de calidad", style={"fontSize": "13px", "marginTop": "16px"}),
                _table(qf.flags(d)),
            ]
            if not rec.empty:
                items += [html.H3("Cierre de volumenes", style={"fontSize": "13px",
                                                                "marginTop": "16px"}),
                          _table(rec)]
            if not sign.empty:
                items += [html.H3("Control de signo nativo", style={"fontSize": "13px",
                                                                    "marginTop": "16px"}),
                          _table(sign)]
            return html.Div(items)
        return html.Div()

    @app.callback(Output("fc-e", "disabled"),
                  Output("fc-volume", "disabled"),
                  Output("fc-head", "disabled"),
                  Output("fc-e", "value"),
                  Output("fc-e-label", "children"),
                  Output("fc-storage-help", "children"),
                  Input("fc-energy-mode", "value"),
                  Input("fc-volume", "value"),
                  Input("fc-head", "value"),
                  Input("fc-eff-t", "value"))
    def toggle_storage_inputs(mode, volume, head, eff_t):
        state = _storage_control_state(mode, volume, head, eff_t)
        mwh_value = state["calculated_mwh"] if mode == "reservoir" else no_update
        return (state["mwh_disabled"], state["volume_disabled"],
                state["head_disabled"], mwh_value, state["mwh_label"], state["help"])

    @app.callback(Output("fc-output", "children"),
                  Input("fc-run", "n_clicks"),
                  State("fc-pt", "value"), State("fc-pb", "value"),
                  State("fc-energy-mode", "value"), State("fc-e", "value"),
                  State("fc-volume", "value"), State("fc-head", "value"),
                  State("fc-eff-t", "value"), State("fc-eff-p", "value"),
                  State("fc-availability", "value"), State("fc-cycles", "value"),
                  State("fc-var-opex", "value"), State("fc-fixed-opex", "value"),
                  State("fc-ssaa", "value"), State("fc-arb-growth", "value"),
                  State("fc-ssaa-growth", "value"), State("fc-start-year", "value"),
                  State("fc-end-year", "value"), State("f-start", "date"),
                  State("f-end", "date"),
                  prevent_initial_call=True)
    def run_forecast(_n, pt, pb, energy_mode, e, volume, head, eff_t, eff_p,
                     availability, cycles, var_opex, fixed_opex, ssaa,
                     arb_growth, ssaa_growth, start_year, end_year,
                     hist_start, hist_end):
        theme_ = LIGHT
        try:
            pt = float(pt); pb = float(pb)
            eff_t = float(eff_t); eff_p = float(eff_p)
            if energy_mode == "reservoir":
                storage = storage_from_inputs(volume_hm3=float(volume), net_head_m=float(head),
                                              turbine_efficiency=eff_t)
            else:
                storage = storage_from_inputs(usable_output_mwh=float(e), turbine_efficiency=eff_t)
            cfg = StorageConfig(
                p_turbine_mw=pt, p_pump_mw=pb, energy_mwh=storage["hydraulic_mwh"],
                rte=eff_t * eff_p, eff_turbine=eff_t, eff_pump=eff_p,
                availability_pct=float(availability), max_cycles_day=float(cycles),
                soc_init_frac=0.5, soc_final_frac=0.5,
            )
            cfg.validate()
            start_year = int(start_year); end_year = int(end_year)
        except (TypeError, ValueError) as exc:
            return html.Div(f"Revisa los parámetros: {exc}",
                            style={"padding": "12px", "borderRadius": "8px",
                                   "background": "#FFF4E5", "color": "#7A4A00"})

        pmd = store.read("pmd")
        if pmd.empty:
            return html.Div("No hay precios históricos. Ejecuta ACTUALIZAR_DATOS.bat y reinicia el dashboard.")
        pmd = pmd.copy()
        pmd["day"] = pd.to_datetime(pmd["day"])
        if hist_start:
            pmd = pmd[pmd["day"] >= pd.Timestamp(hist_start)]
        if hist_end:
            pmd = pmd[pmd["day"] < pd.Timestamp(hist_end) + pd.Timedelta(days=1)]
        if pmd.empty:
            return html.Div("No hay precios en el periodo histórico seleccionado.")
        pmd["ts"] = pmd["day"] + pd.to_timedelta((pmd["qh"] - 1) * 15, unit="m")
        hourly_prices = pmd.groupby(pmd["ts"].dt.floor("h"))["pmd"].mean().sort_index()
        historical_days = max((hourly_prices.index.max() - hourly_prices.index.min()).days + 1, 1)

        ancillary_reference = 0.0
        base_detail = detail.copy()
        if hist_start:
            base_detail = base_detail[base_detail["datetime"] >= pd.Timestamp(hist_start)]
        if hist_end:
            base_detail = base_detail[base_detail["datetime"] < pd.Timestamp(hist_end) + pd.Timedelta(days=1)]
        if not base_detail.empty:
            observed = add_group(base_detail)
            ancillary = observed[observed["grupo"].isin([
                "RR", "mFRR", "Restricciones diario", "Restricciones tiempo real", "aFRR banda"
            ])]
            if not ancillary.empty:
                by_asset = ancillary.groupby("asset")["revenue_incremental"].sum()
                mw = pd.to_numeric(assets.set_index("asset")["mw_reference"], errors="coerce")
                per_mw = (by_asset / mw).replace([np.inf, -np.inf], np.nan).dropna()
                detail_days = max((base_detail["datetime"].max() - base_detail["datetime"].min()).days + 1, 1)
                if not per_mw.empty:
                    ancillary_reference = float(per_mw.median()) * 365.25 / detail_days

        try:
            projection, operations = annual_projection(
                hourly_prices, cfg, start_year=start_year, end_year=end_year,
                ancillary_eur_mw_year=ancillary_reference, ancillary_level=ssaa,
                arbitrage_growth_pct=float(arb_growth or 0),
                ancillary_growth_pct=float(ssaa_growth or 0),
                variable_opex_eur_mwh=float(var_opex or 0),
                fixed_opex_eur_kw_year=float(fixed_opex or 0),
            )
        except (RuntimeError, ValueError) as exc:
            return html.Div(f"No se pudo resolver el escenario: {exc}",
                            style={"padding": "12px", "borderRadius": "8px",
                                   "background": "#FDECEC", "color": "#8A1C1C"})

        base_first = projection[(projection["anio"] == start_year)
                                & (projection["escenario"] == "Base")].iloc[0]
        useful_mwh = storage["usable_output_mwh"]
        duration = useful_mwh / pt
        notes = []
        if historical_days < 90:
            notes.append(f"El backtest contiene solo {historical_days} días; amplía el histórico antes de una decisión de inversión.")
        if ancillary_reference == 0:
            notes.append("No se ha podido obtener una referencia observada de servicios de ajuste; SSAA se muestra a cero.")
        if operations["simultaneidad_detectada"].any():
            notes.append("Se detectó una operación incompatible de bombeo y turbinación simultáneos; revisa los límites operativos.")

        assumptions = pd.DataFrame([
            {"Parámetro": "Capacidad eléctrica útil", "Valor": f"{useful_mwh:,.0f} MWh"},
            {"Parámetro": "Duración a potencia nominal", "Valor": f"{duration:,.2f} h"},
            {"Parámetro": "Capacidad hidráulica del modelo", "Valor": f"{storage['hydraulic_mwh']:,.0f} MWh"},
            {"Parámetro": "Origen del almacenamiento", "Valor": storage["source"]},
            {"Parámetro": "Rendimiento de ciclo", "Valor": f"{eff_t * eff_p:.1%}"},
            {"Parámetro": "Histórico de referencia", "Valor": f"{hourly_prices.index.min():%d/%m/%Y} – {hourly_prices.index.max():%d/%m/%Y}"},
            {"Parámetro": "Referencia SSAA mediana", "Valor": f"{ancillary_reference:,.0f} €/MW·año"},
            {"Parámetro": "Crecimiento anual arbitraje / SSAA", "Valor": f"{float(arb_growth or 0):.1f}% / {float(ssaa_growth or 0):.1f}%"},
        ])
        operations_view = operations.rename(columns={
            "escenario": "Escenario",
            "precio_medio_venta_eur_mwh": "Venta €/MWh",
            "precio_medio_compra_eur_mwh": "Compra €/MWh",
            "spread_capturado_eur_mwh": "Spread €/MWh",
            "generacion_mwh_anio": "Generación MWh/año",
            "bombeo_mwh_anio": "Bombeo MWh/año",
            "ciclos_equivalentes_anio": "Ciclos/año",
            "factor_utilizacion_pct": "Utilización %",
            "simultaneidad_detectada": "Simultáneo",
        })
        operations_view["Simultáneo"] = operations_view["Simultáneo"].map({True: "Sí", False: "No"})
        projection_view = projection.rename(columns={
            "anio": "Año", "escenario": "Escenario",
            "arbitraje_eur": "Arbitraje €", "ssaa_eur": "SSAA €",
            "opex_variable_eur": "OPEX variable €", "opex_fijo_eur": "OPEX fijo €",
            "ingreso_neto_eur": "Ingreso neto €", "eur_mw_anio": "€/MW·año",
            "eur_mwh_almacenamiento_anio": "€/MWh almacenado·año",
        })

        return html.Div([
            html.Div([
                _stat("Ingreso neto base", f"{base_first['ingreso_neto_eur'] / 1_000_000:,.2f} M€",
                      f"año {start_year}", theme_),
                _stat("Ritmo neto", f"{base_first['eur_mw_anio']:,.0f} €/MW·año",
                      "escenario base", theme_),
                _stat("Ingreso por almacenamiento", f"{base_first['eur_mwh_almacenamiento_anio']:,.0f} €/MWh·año",
                      f"{useful_mwh:,.0f} MWh útiles", theme_),
                _stat("Duración", f"{duration:,.1f} h", f"{pt:,.0f} MW turbinado", theme_),
            ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                      "marginBottom": "16px"}),
            *([html.Div([html.Strong("Advertencias: "), " ".join(notes)],
                        style={"padding": "11px 13px", "borderRadius": "8px",
                               "background": "#FFF4E5", "color": "#704200",
                               "fontSize": "12px", "marginBottom": "14px"})] if notes else []),
            html.Div([
                dcc.Graph(figure=forecast_figure(projection, theme_),
                          config={"displayModeBar": False}, style={"flex": "1 1 560px"}),
                dcc.Graph(figure=forecast_stack_figure(projection, theme_, start_year),
                          config={"displayModeBar": False}, style={"flex": "1 1 440px"}),
            ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
            html.H3("Operación anualizada del backtest", style={"fontSize": "13px", "marginTop": "14px"}),
            _table(operations_view),
            html.H3("Supuestos aplicados", style={"fontSize": "13px", "marginTop": "16px"}),
            _table(assumptions),
            html.Details([
                html.Summary("Detalle anual de resultados", style={"cursor": "pointer", "fontWeight": 600}),
                html.Div(_table(projection_view), style={"marginTop": "10px"}),
            ], style={"marginTop": "16px"}),
            html.Div("Modelo de escenarios: backtest histórico optimizado + supuestos de crecimiento introducidos. "
                     "No incorpora CAPEX, financiación, impuestos, hidrología ni restricciones ambientales.",
                     style={"fontSize": "11.5px", "color": theme_["text_muted"], "marginTop": "14px"}),
        ])

    return app
