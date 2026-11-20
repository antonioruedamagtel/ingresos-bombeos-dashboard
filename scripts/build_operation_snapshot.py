"""Construye una reconstrucción compacta de operación por activo para la demo.

El resultado usa el programa físico P48 y anotaciones I90 por unidad de
programación. No es telemetría de planta ni permite asignar una causa a un cero.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ib.domain.aliases import AliasTable
from ib.pipeline import load_assets

OUT = ROOT / "docs" / "data" / "operation-data.json"
CACHE = ROOT / "data" / "normalized" / "i90"
EPS = 0.01

# Bit mask of REE/e·sios annotations. These mean programme or service activity,
# not necessarily a bilateral sale or an independently settled revenue at that hour.
MARKETS = {
    "I90DIA02": (1, "P48 / programa final"),
    "I90DIA03": (2, "RRTT / ECO diario"),
    "I90DIA05": (4, "aFRR banda"),
    "I90DIA06": (8, "RR"),
    "I90DIA07": (16, "mFRR"),
    "I90DIA08": (32, "RRTT / desvíos TR"),
}


def mode(gen: float, pump: float) -> str:
    if gen > EPS and pump > EPS:
        return "mixto"
    if gen > EPS:
        return "turbinando"
    if pump > EPS:
        return "bombeando"
    return "sin_programa"


def quantize(power: float) -> float:
    return float(round(power / 5.0) * 5.0) if power > EPS else 0.0


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else 0.0


def main() -> None:
    assets = load_assets(ROOT / "config" / "assets.csv")
    aliases = AliasTable.from_assets(assets)
    names = assets["asset"].tolist()
    asset_id = {name: index for index, name in enumerate(names)}
    role_by_up = {alias.code: (alias.asset, alias.role) for alias in aliases.aliases}

    files = sorted(CACHE.rglob("*.parquet"))
    if not files:
        raise RuntimeError("No existe caché I90 normalizada.")

    days: list[str] = []
    detailed: list[pd.DataFrame] = []
    hourly_rows: list[list] = []
    data_status: dict[str, bool] = {}

    for number, path in enumerate(files, 1):
        day = path.stem
        if len(day) != 8 or not day.isdigit():
            continue
        iso_day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        days.append(iso_day)
        frame = pd.read_parquet(path)
        if frame.empty:
            data_status[iso_day] = False
            continue
        frame["up"] = frame["up"].astype(str).str.upper().str.strip()
        selected = frame[frame["up"].isin(role_by_up)].copy()
        data_status[iso_day] = not selected.empty
        if selected.empty:
            continue
        selected["asset"] = selected["up"].map(lambda item: role_by_up[item][0])
        selected["role"] = selected["up"].map(lambda item: role_by_up[item][1])
        selected["hour"] = ((selected["period"].astype(int) - 1) // 4).astype(int)
        selected["qh"] = selected["period"].astype(int)

        # P48 is the final programme and published in MW in the underlying I90 sheet.
        p48 = selected[selected["sheet"] == "I90DIA02"].copy()
        if not p48.empty:
            p48["mw"] = p48["value"].abs()
            grouped = p48.groupby(["asset", "role", "qh", "hour"], as_index=False)["mw"].sum()
            # Conservamos esta pequeña rejilla, no el I90 original: será la
            # base de bloques y horas de operación a cuarto de hora.
            detail = p48.groupby(["asset", "role", "qh"], as_index=False)["mw"].sum()
            detail["day_index"] = len(days) - 1
            detailed.append(detail[["asset", "role", "day_index", "qh", "mw"]])

        activity = selected[selected["sheet"].isin(MARKETS)].copy()
        if not activity.empty:
            activity = activity[activity["value"].abs() > EPS]
            activity["bit"] = activity["sheet"].map(lambda item: MARKETS[item][0])
            masks = activity.groupby(["asset", "hour"], as_index=False)["bit"].agg(lambda bits: int(np.bitwise_or.reduce(bits.to_numpy(dtype=int))))
        else:
            masks = pd.DataFrame(columns=["asset", "hour", "bit"])

        pivot = grouped.pivot_table(index=["asset", "hour"], columns="role", values="mw", aggfunc="sum", fill_value=0).reset_index() if not p48.empty else pd.DataFrame(columns=["asset", "hour"])
        for role in ("generation", "pumping"):
            if role not in pivot:
                pivot[role] = 0.0
        pivot = pivot.merge(masks, on=["asset", "hour"], how="outer").fillna(0)
        for row in pivot.itertuples(index=False):
            gen, pump, bit = float(getattr(row, "generation", 0)), float(getattr(row, "pumping", 0)), int(getattr(row, "bit", 0))
            if gen > EPS or pump > EPS or bit:
                hourly_rows.append([asset_id[row.asset], len(days) - 1, int(row.hour), round(gen, 3), round(pump, 3), bit])
        if number % 100 == 0:
            print(f"{number}/{len(files)} días", flush=True)

    # Full QH grid only for selected plants. This enables truthful operating-duration
    # and fixed-setpoint blocks without publishing raw unit-level source data.
    if not detailed:
        raise RuntimeError("No se encontraron programas P48 de los activos configurados.")
    base = pd.concat(detailed, ignore_index=True)
    qh = base.groupby(["asset", "role", "day_index", "qh"], as_index=False)["mw"].sum()
    qh = qh.pivot_table(index=["asset", "day_index", "qh"], columns="role", values="mw", aggfunc="sum", fill_value=0).reset_index()
    for role in ("generation", "pumping"):
        if role not in qh:
            qh[role] = 0.0
    qh["mode"] = [mode(g, p) for g, p in zip(qh["generation"], qh["pumping"])]
    qh["power"] = qh[["generation", "pumping"]].max(axis=1)
    qh["setpoint"] = qh["power"].map(quantize)

    daily = []
    block_rows = []
    for asset in names:
        g = qh[qh["asset"] == asset].sort_values(["day_index", "qh"]).copy()
        by_day = {int(day_index): frame.copy() for day_index, frame in g.groupby("day_index", sort=False)}
        # También se emiten los días sin ningún P48 de la central: son justo
        # los que permiten estudiar esperas/paradas, sin atribuirles una causa.
        for day_index, iso_day in enumerate(days):
            d = by_day.get(day_index, pd.DataFrame(columns=g.columns)).copy()
            observed_qh = set(d["qh"].astype(int).tolist())
            # Missing quarters are treated as no programme only when the day had an I90 publication.
            published = data_status.get(iso_day, False)
            gen_h = float((d["generation"] > EPS).sum() / 4)
            pump_h = float((d["pumping"] > EPS).sum() / 4)
            mixed_h = float(((d["generation"] > EPS) & (d["pumping"] > EPS)).sum() / 4)
            idle_h = max(0.0, 24.0 - float(len(observed_qh) / 4)) if published else None
            gen_values = d.loc[d["generation"] > EPS, "generation"].tolist()
            pump_values = d.loc[d["pumping"] > EPS, "pumping"].tolist()
            daily.append([asset_id[asset], int(day_index), round(gen_h, 2), round(pump_h, 2),
                          None if idle_h is None else round(idle_h, 2), round(mixed_h, 2),
                          round(float(d["generation"].sum()) / 4, 3), round(float(d["pumping"].sum()) / 4, 3),
                          round(percentile(gen_values, 50), 2), round(percentile(pump_values, 50), 2), int(published)])

            # Consecutive active 15-minute blocks by mode and 5-MW setpoint.
            # A gap in P48 always cuts the block, even though it is not
            # published as a separate zero row for that central.
            d = d.sort_values("qh").copy()
            d["block_key"] = d["mode"].astype(str) + "|" + d["setpoint"].astype(str)
            d["block"] = ((d["block_key"] != d["block_key"].shift()) | (d["qh"].diff().fillna(1) != 1)).cumsum()
            for (_, key), b in d.groupby(["block", "block_key"]):
                m = b["mode"].iloc[0]
                if m == "sin_programa":
                    continue
                block_rows.append((asset, m, float(b["setpoint"].iloc[0]), len(b) / 4))

    blocks = pd.DataFrame(block_rows, columns=["asset", "mode", "setpoint_mw", "hours"])
    block_stats = []
    for (asset, operating_mode, setpoint), b in blocks.groupby(["asset", "mode", "setpoint_mw"], sort=False):
        values = b["hours"].tolist()
        block_stats.append([asset_id[asset], operating_mode, round(float(setpoint), 1), len(values),
                            round(float(np.mean(values)), 2), round(percentile(values, 50), 2),
                            round(percentile(values, 90), 2), round(float(np.max(values)), 2),
                            round(float(sum(values)), 2)])

    payload = {
        "metadata": {
            "period_start": days[0], "period_end": days[-1], "granularity": "15min->hora",
            "source": "REE/e·sios I90DIA02, 03, 05, 06, 07 y 08",
            "caveat": "Reconstrucción de programa y anotaciones por UP; no telemetría SCADA ni causa de parada.",
        },
        "assets": names,
        "days": days,
        "markets": {str(bit): label for bit, label in MARKETS.values()},
        "hourly_columns": ["asset_id", "day_id", "hora", "mw_turbinacion", "mw_bombeo", "mercados_mask"],
        "hourly": hourly_rows,
        "daily_columns": ["asset_id", "day_id", "h_turbinando", "h_bombeando", "h_sin_programa", "h_mixto", "mwh_generacion", "mwh_bombeo", "p50_mw_turb", "p50_mw_bomb", "publicado"],
        "daily": daily,
        "block_columns": ["asset_id", "modo", "setpoint_mw_5", "bloques", "duracion_media_h", "p50_h", "p90_h", "max_h", "horas_totales"],
        "blocks": block_stats,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(encoded, encoding="utf-8")
    OUT.with_suffix(".js").write_text(f"window.OPERATION_DATA={encoded};\n", encoding="utf-8")
    print(f"{OUT} · {OUT.stat().st_size:,} bytes · {len(days)} días · {len(hourly_rows):,} horas activas")


if __name__ == "__main__":
    main()
