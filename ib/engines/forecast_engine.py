"""Motor prospectivo: backtest sintético, optimización de despacho y escenarios.

Diseño en cuatro niveles, tal y como se pidió:

  Nivel 1  selección de comparables físicos entre las centrales observadas.
  Nivel 2  backtest histórico: se aplica la configuración técnica de la CHR
           futura sobre precios reales de años pasados.
  Nivel 3  optimización de despacho con restricciones reales, no reglas del
           tipo "bombear las cuatro horas más baratas".
  Nivel 4  servicios de ajuste por escenario, nunca extrapolando el €/MW de
           una central concreta sin justificarlo.
  Nivel 5  proyección con bandas de incertidumbre, jamás determinista.

Elección de solver, documentada: primero se resuelve la relajación lineal con
HiGHS a través de `scipy.optimize.linprog`. Si aparecen bombeo y turbinación
simultáneos —algo económicamente posible con precios negativos— se rehace el
despacho como MILP mediante `scipy.optimize.milp`, con una variable binaria por
periodo que impone exclusión mutua. Así se conserva la velocidad en los casos
ordinarios sin sacrificar coherencia física en escenarios extremos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import csr_matrix, hstack, vstack


@dataclass
class StorageConfig:
    p_turbine_mw: float
    p_pump_mw: float
    energy_mwh: float                 # capacidad útil del embalse superior
    rte: float = 0.78                 # rendimiento de ciclo completo
    eff_turbine: float | None = None
    eff_pump: float | None = None
    soc_init_frac: float = 0.5
    soc_final_frac: float | None = 0.5
    soc_min_frac: float = 0.0
    soc_max_frac: float = 1.0
    ramp_mw_per_min: float | None = None
    self_discharge_pct_day: float = 0.0
    availability_pct: float = 100.0
    max_cycles_day: float | None = None

    def efficiencies(self) -> tuple[float, float]:
        if self.eff_turbine and self.eff_pump:
            return float(self.eff_turbine), float(self.eff_pump)
        e = float(np.sqrt(max(self.rte, 1e-6)))
        return e, e

    def validate(self) -> None:
        """Valida los límites físicos antes de construir el problema de despacho."""
        for name, value in {
            "potencia de turbinado": self.p_turbine_mw,
            "potencia de bombeo": self.p_pump_mw,
            "almacenamiento": self.energy_mwh,
        }.items():
            if value is None or not np.isfinite(value) or float(value) <= 0:
                raise ValueError(f"La {name} debe ser mayor que cero.")
        if not 0 < float(self.rte) <= 1:
            raise ValueError("El rendimiento de ciclo debe estar entre 0 y 1.")
        if not 0 <= float(self.availability_pct) <= 100:
            raise ValueError("La disponibilidad debe estar entre 0 y 100 %.")
        if not (0 <= self.soc_min_frac <= self.soc_init_frac <= self.soc_max_frac <= 1):
            raise ValueError("Los límites de almacenamiento y el estado inicial no son coherentes.")
        if self.soc_final_frac is not None and not self.soc_min_frac <= self.soc_final_frac <= self.soc_max_frac:
            raise ValueError("El estado final debe quedar dentro de los límites de almacenamiento.")
        if self.max_cycles_day is not None and self.max_cycles_day <= 0:
            raise ValueError("El máximo de ciclos diarios debe ser mayor que cero.")


def reservoir_potential_mwh(volume_hm3: float, net_head_m: float) -> float:
    """Energía hidráulica potencial de una balsa en MWh.

    Un hm³ equivale a un millón de m³. La conversión usa rho=1.000 kg/m³,
    g=9,81 m/s² y 3,6 GJ/MWh. El resultado es energía hidráulica antes de la
    turbina; la energía eléctrica útil se obtiene multiplicando por su
    eficiencia.
    """
    if volume_hm3 is None or net_head_m is None or volume_hm3 <= 0 or net_head_m <= 0:
        raise ValueError("El volumen útil y el salto neto deben ser mayores que cero.")
    return float(1000.0 * 9.81 * volume_hm3 * 1_000_000.0 * net_head_m / 3_600_000_000.0)


def storage_from_inputs(*, usable_output_mwh: float | None = None,
                        volume_hm3: float | None = None, net_head_m: float | None = None,
                        turbine_efficiency: float = 0.90) -> dict:
    """Normaliza una capacidad eléctrica o una geometría de balsa.

    ``StorageConfig.energy_mwh`` conserva la convención histórica del motor:
    energía hidráulica potencial. Para una capacidad eléctrica declarada se
    deshace la eficiencia de turbinado; para una balsa se calcula primero la
    energía potencial y después la energía eléctrica entregable.
    """
    if not 0 < turbine_efficiency <= 1:
        raise ValueError("La eficiencia de turbinado debe estar entre 0 y 1.")
    if usable_output_mwh is not None:
        if usable_output_mwh <= 0:
            raise ValueError("La capacidad útil en MWh debe ser mayor que cero.")
        hydraulic = float(usable_output_mwh) / float(turbine_efficiency)
        usable = float(usable_output_mwh)
        source = "capacidad eléctrica introducida"
    else:
        hydraulic = reservoir_potential_mwh(float(volume_hm3), float(net_head_m))
        usable = hydraulic * float(turbine_efficiency)
        source = "volumen útil × salto neto"
    return {
        "hydraulic_mwh": hydraulic,
        "usable_output_mwh": usable,
        "source": source,
    }


def optimize_dispatch(prices: pd.Series, cfg: StorageConfig, dt_hours: float = 1.0) -> pd.DataFrame:
    """Despacho óptimo de arbitraje puro contra una serie de precios.

    prices: serie indexada por tiempo, en euros por MWh.
    Devuelve generación, bombeo, estado de carga y caja por periodo.
    """
    cfg.validate()
    p = np.asarray(prices, dtype=float)
    T = len(p)
    if T == 0:
        return pd.DataFrame()
    eff_t, eff_p = cfg.efficiencies()
    avail = max(min(cfg.availability_pct / 100.0, 1.0), 0.0)
    Pg = cfg.p_turbine_mw * avail
    Pb = cfg.p_pump_mw * avail
    Smax = cfg.energy_mwh * cfg.soc_max_frac
    Smin = cfg.energy_mwh * cfg.soc_min_frac
    S0 = cfg.energy_mwh * cfg.soc_init_frac
    loss = cfg.self_discharge_pct_day / 100.0 * dt_hours / 24.0

    # x = [g_0..g_{T-1}, b_0..b_{T-1}, s_0..s_{T-1}]
    n = 3 * T
    c = np.zeros(n)
    c[:T] = -p * dt_hours            # maximizar ingreso de generación
    c[T:2 * T] = p * dt_hours        # minimizar coste de bombeo

    rows, cols, vals, beq = [], [], [], []
    for t in range(T):
        r = t
        rows += [r, r, r]
        cols += [2 * T + t, t, T + t]
        vals += [1.0, dt_hours / eff_t, -dt_hours * eff_p]
        if t == 0:
            beq.append(S0 * (1 - loss))
        else:
            rows.append(r); cols.append(2 * T + t - 1); vals.append(-(1 - loss))
            beq.append(0.0)
    Aeq = csr_matrix((vals, (rows, cols)), shape=(T, n))

    r_rows, r_cols, r_vals, r_b = [], [], [], []
    k = 0
    if cfg.ramp_mw_per_min:
        ramp = cfg.ramp_mw_per_min * dt_hours * 60.0
        for t in range(1, T):
            for sgn in (1.0, -1.0):
                r_rows += [k, k, k, k]
                r_cols += [t, T + t, t - 1, T + t - 1]
                r_vals += [sgn, -sgn, -sgn, sgn]
                r_b.append(ramp)
                k += 1

    if cfg.max_cycles_day is not None:
        # Un ciclo equivalente se define sobre la energía eléctrica útil que
        # puede entregar el embalse, no sobre el consumo de bombeo.
        usable_capacity = cfg.energy_mwh * eff_t
        idx = pd.DatetimeIndex(prices.index)
        for day in pd.unique(idx.normalize()):
            positions = np.flatnonzero(idx.normalize() == day)
            for t in positions:
                r_rows.append(k); r_cols.append(int(t)); r_vals.append(dt_hours)
            r_b.append(usable_capacity * float(cfg.max_cycles_day))
            k += 1

    A_ub = csr_matrix((r_vals, (r_rows, r_cols)), shape=(k, n)) if k else None
    b_ub = np.array(r_b) if k else None

    bounds = [(0, Pg)] * T + [(0, Pb)] * T + [(Smin, Smax)] * T
    if cfg.soc_final_frac is not None:
        sf = cfg.energy_mwh * cfg.soc_final_frac
        bounds[-1] = (sf, sf)

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=Aeq, b_eq=np.array(beq),
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"Optimización de despacho no resuelta: {res.message}")
    x = res.x

    # La relajación LP puede aprovechar las pérdidas del ciclo durante horas
    # negativas y consumir energía bombeando y turbinando a la vez. Si ocurre,
    # se activa una formulación MILP exacta con y_t=1 en modo generación y
    # y_t=0 en modo bombeo.
    if np.any((x[:T] > 1e-6) & (x[T:2 * T] > 1e-6)):
        n_milp = 4 * T
        c_milp = np.concatenate([c, np.zeros(T)])
        zero_binary = csr_matrix((T, T))
        constraints = [LinearConstraint(hstack([Aeq, zero_binary], format="csr"),
                                        np.asarray(beq), np.asarray(beq))]

        if A_ub is not None:
            padded_ub = hstack([A_ub, csr_matrix((A_ub.shape[0], T))], format="csr")
            constraints.append(LinearConstraint(padded_ub, -np.inf, b_ub))

        # g_t <= Pg*y_t; b_t <= Pb*(1-y_t).
        m_rows, m_cols, m_vals = [], [], []
        for t in range(T):
            m_rows += [2 * t, 2 * t, 2 * t + 1, 2 * t + 1]
            m_cols += [t, 3 * T + t, T + t, 3 * T + t]
            m_vals += [1.0, -Pg, 1.0, Pb]
        mutual = csr_matrix((m_vals, (m_rows, m_cols)), shape=(2 * T, n_milp))
        mutual_ub = np.tile(np.array([0.0, Pb]), T)
        constraints.append(LinearConstraint(mutual, -np.inf, mutual_ub))

        lower = np.array([b[0] for b in bounds] + [0.0] * T, dtype=float)
        upper = np.array([b[1] for b in bounds] + [1.0] * T, dtype=float)
        integrality = np.concatenate([np.zeros(3 * T, dtype=int), np.ones(T, dtype=int)])
        exact = milp(c_milp, integrality=integrality, bounds=Bounds(lower, upper),
                     constraints=constraints, options={"presolve": True})
        if not exact.success:
            raise RuntimeError(f"Optimización física MILP no resuelta: {exact.message}")
        x = exact.x[:3 * T]
    out = pd.DataFrame({
        "datetime": pd.Index(prices.index),
        "price": p,
        "generation_mw": x[:T],
        "pumping_mw": x[T:2 * T],
        "soc_mwh": x[2 * T:],
    })
    out["generation_mwh"] = out["generation_mw"] * dt_hours
    out["pumping_mwh"] = out["pumping_mw"] * dt_hours
    out["cashflow"] = (out["generation_mwh"] - out["pumping_mwh"]) * out["price"]
    out["simultaneous"] = (out["generation_mw"] > 1e-6) & (out["pumping_mw"] > 1e-6)
    return out


def dispatch_metrics(disp: pd.DataFrame, cfg: StorageConfig) -> dict:
    gen = disp["generation_mwh"].sum()
    pum = disp["pumping_mwh"].sum()
    revenue = (disp["generation_mwh"] * disp["price"]).sum()
    cost = (disp["pumping_mwh"] * disp["price"]).sum()
    hours = len(disp) * (disp["datetime"].diff().dt.total_seconds().dropna().median() / 3600 if len(disp) > 1 else 1)
    eff_t, _ = cfg.efficiencies()
    useful_capacity = cfg.energy_mwh * eff_t
    cycles = gen / useful_capacity if useful_capacity else np.nan
    return {
        "generacion_mwh": gen,
        "bombeo_mwh": pum,
        "arbitraje_eur": revenue - cost,
        "precio_medio_venta": revenue / gen if gen else np.nan,
        "precio_medio_compra": cost / pum if pum else np.nan,
        "spread_efectivo": (revenue / gen - cost / pum) if gen and pum else np.nan,
        "ciclos_equivalentes": cycles,
        "factor_utilizacion": gen / (cfg.p_turbine_mw * hours) if cfg.p_turbine_mw and hours else np.nan,
        "horas": hours,
        "simultaneidad_detectada": bool(disp["simultaneous"].any()),
    }


def annual_projection(prices: pd.Series, cfg: StorageConfig, *, start_year: int,
                      end_year: int, ancillary_eur_mw_year: float = 0.0,
                      ancillary_level: str = "Central", arbitrage_growth_pct: float = 0.0,
                      ancillary_growth_pct: float = 0.0,
                      variable_opex_eur_mwh: float = 0.0,
                      fixed_opex_eur_kw_year: float = 0.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Proyecta escenarios auditables a partir de un backtest histórico.

    El optimizador se ejecuta una vez por escenario sobre la forma histórica.
    Después se aplican, de forma explícita, los crecimientos anuales elegidos
    por el usuario. No pretende ser una curva de precios de mercado ni una
    valoración bancaria; es un modelo de escenarios trazable.
    """
    if end_year < start_year:
        raise ValueError("El año final debe ser igual o posterior al inicial.")
    clean = pd.Series(prices, dtype=float).dropna().sort_index()
    if len(clean) < 24:
        raise ValueError("Se necesitan al menos 24 precios horarios para el backtest.")
    span_hours = max((clean.index.max() - clean.index.min()).total_seconds() / 3600.0 + 1.0, 1.0)
    annual_factor = 365.25 * 24.0 / span_hours
    ancillary_factor = ANCILLARY_SCENARIOS.get(ancillary_level, 1.0)
    scenario_ancillary = {"Low": 0.70, "Base": 1.00, "High": 1.30}

    projection_rows: list[dict] = []
    operation_rows: list[dict] = []
    for name, scenario in DEFAULT_SCENARIOS.items():
        scenario_prices = apply_scenario(clean, scenario)
        dispatch = optimize_dispatch(scenario_prices, cfg)
        metrics = dispatch_metrics(dispatch, cfg)
        base_arbitrage = float(metrics["arbitraje_eur"]) * annual_factor
        annual_generation = float(metrics["generacion_mwh"]) * annual_factor
        annual_pumping = float(metrics["bombeo_mwh"]) * annual_factor
        base_variable_opex = (annual_generation + annual_pumping) * float(variable_opex_eur_mwh)
        fixed_opex = cfg.p_turbine_mw * 1000.0 * float(fixed_opex_eur_kw_year)
        base_ancillary = (float(ancillary_eur_mw_year) * cfg.p_turbine_mw
                          * ancillary_factor * scenario_ancillary[name])

        operation_rows.append({
            "escenario": name,
            "precio_medio_venta_eur_mwh": metrics["precio_medio_venta"],
            "precio_medio_compra_eur_mwh": metrics["precio_medio_compra"],
            "spread_capturado_eur_mwh": metrics["spread_efectivo"],
            "generacion_mwh_anio": annual_generation,
            "bombeo_mwh_anio": annual_pumping,
            "ciclos_equivalentes_anio": metrics["ciclos_equivalentes"] * annual_factor,
            "factor_utilizacion_pct": metrics["factor_utilizacion"] * 100.0,
            "simultaneidad_detectada": metrics["simultaneidad_detectada"],
        })

        for year in range(int(start_year), int(end_year) + 1):
            n = year - int(start_year)
            arbitrage = base_arbitrage * (1.0 + float(arbitrage_growth_pct) / 100.0) ** n
            ancillary = base_ancillary * (1.0 + float(ancillary_growth_pct) / 100.0) ** n
            variable_opex = base_variable_opex
            net = arbitrage + ancillary - variable_opex - fixed_opex
            projection_rows.append({
                "anio": year,
                "escenario": name,
                "arbitraje_eur": arbitrage,
                "ssaa_eur": ancillary,
                "opex_variable_eur": variable_opex,
                "opex_fijo_eur": fixed_opex,
                "ingreso_neto_eur": net,
                "eur_mw_anio": net / cfg.p_turbine_mw,
                "eur_mwh_almacenamiento_anio": net / (cfg.energy_mwh * cfg.efficiencies()[0]),
            })
    return pd.DataFrame(projection_rows), pd.DataFrame(operation_rows)


# ---------------------------------------------------------------- comparables
def select_comparables(target: dict, observed: pd.DataFrame, k: int = 3) -> pd.DataFrame:
    """Nivel 1. Comparables por similitud física normalizada."""
    feats = ["potencia_turbinado_mw", "horas_equivalentes", "round_trip_efficiency", "almacenamiento_gwh"]
    d = observed.copy()
    score = pd.Series(0.0, index=d.index)
    used = 0
    for f in feats:
        if f not in d.columns or f not in target or target[f] in (None, "UNKNOWN"):
            continue
        v = pd.to_numeric(d[f], errors="coerce")
        if v.notna().sum() < 2:
            continue
        ref = float(target[f])
        rng = max(v.max() - v.min(), 1e-9)
        score += ((v - ref).abs() / rng).fillna(1.0)
        used += 1
    if used == 0:
        return d.head(k).assign(similitud=np.nan)
    d["similitud"] = 1.0 - score / used
    return d.sort_values("similitud", ascending=False).head(k)


# ------------------------------------------------------------------ escenarios
@dataclass
class PriceScenario:
    name: str
    mean_shift_pct: float = 0.0        # variación del precio medio
    volatility_factor: float = 1.0     # escalado de la dispersión intradiaria
    zero_hours_pct: float | None = None
    negative_hours_pct: float | None = None
    notes: str = ""


def apply_scenario(prices: pd.Series, sc: PriceScenario) -> pd.Series:
    """Transforma una forma histórica de precios según el escenario.

    Se conserva la forma horaria real y se ajustan nivel y dispersión. Es
    deliberadamente simple y auditable: cualquier modelo más sofisticado debe
    justificarse contra datos, no sustituir esta transformación por defecto.
    """
    p = pd.Series(np.asarray(prices, dtype=float), index=prices.index)
    daily = p.groupby(p.index.date).transform("mean")
    spread = p - daily
    out = daily * (1 + sc.mean_shift_pct / 100.0) + spread * sc.volatility_factor
    if sc.negative_hours_pct is not None and sc.negative_hours_pct > 0:
        q = np.percentile(out, sc.negative_hours_pct)
        out = out.where(out > q, out - abs(q) - 1.0)
    return out


DEFAULT_SCENARIOS = {
    "Low": PriceScenario("Low", mean_shift_pct=-20, volatility_factor=0.8,
                         notes="Menor electrificación y menor volatilidad; spread comprimido."),
    "Base": PriceScenario("Base", mean_shift_pct=0, volatility_factor=1.0,
                          notes="Continuidad de la forma histórica observada."),
    "High": PriceScenario("High", mean_shift_pct=15, volatility_factor=1.4,
                          notes="Alta penetración renovable con más horas extremas; spread ampliado."),
}


ANCILLARY_SCENARIOS = {
    "Conservador": 0.35,
    "Central": 1.00,
    "Alto": 1.60,
}


def ancillary_from_comparables(comparable_eur_mw_year: float, level: str = "Central") -> float:
    """Nivel 4. Ingreso de ajuste por escenario a partir de comparables observados.

    Nunca se asume que una CHR nueva capture el mismo €/MW que Aguayo: el valor
    central es la mediana de los comparables y los escenarios lo modulan.
    """
    f = ANCILLARY_SCENARIOS.get(level, 1.0)
    return float(comparable_eur_mw_year) * f


def uncertainty_band(central: float, low_pct: float = 30.0, high_pct: float = 35.0) -> tuple[float, float]:
    return central * (1 - low_pct / 100.0), central * (1 + high_pct / 100.0)
