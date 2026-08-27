"""Interfaz de linea de comandos.

    python cli.py ingest   --start 2023-01-01 --end 2023-01-31
    python cli.py build    --start 2023-01-01 --end 2023-01-31
    python cli.py qa       --start 2023-01-01 --end 2023-01-31
    python cli.py forecast --mw 500 --hours 8 --rte 0.78
    python cli.py purge-raw
"""
from __future__ import annotations

import argparse
from datetime import date
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent


def _pipeline(args):
    from ib.pipeline import Pipeline
    return Pipeline(Path(args.data), ROOT / "config" / "assets.csv")


def main() -> int:
    ap = argparse.ArgumentParser(description="INGRESOS BOMBEOS")
    ap.add_argument("--data", default=str(ROOT / "data"), help="raiz de datos")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("ingest", "build", "qa"):
        s = sub.add_parser(name)
        s.add_argument("--start", required=True)
        s.add_argument("--end", required=True)

    f = sub.add_parser("forecast")
    f.add_argument("--mw", type=float, required=True)
    f.add_argument("--hours", type=float, required=True)
    f.add_argument("--rte", type=float, default=0.78)
    f.add_argument("--scenario", default="Base", choices=("Low", "Base", "High"))

    sub.add_parser("purge-raw")
    args = ap.parse_args()

    if args.cmd == "ingest":
        p = _pipeline(args)
        st = p.ingest_i90(date.fromisoformat(args.start), date.fromisoformat(args.end))
        print(st["status"].value_counts().to_string())
        return 0

    if args.cmd == "build":
        p = _pipeline(args)
        r = p.build(date.fromisoformat(args.start), date.fromisoformat(args.end))
        print("\nCIERRE DE VOLUMENES")
        print(r["reconciliation"][["entity", "role", "p48", "pbf", "residual",
                                   "residual_pct", "closes"]].round(2).to_string(index=False))
        print("\nCOMPONENTES (EUR)")
        print(r["detail"].groupby(["asset", "market"])["revenue_incremental"]
              .sum().round(0).to_string())
        return 0

    if args.cmd == "qa":
        from ib.qa import quality_flags as qf
        from ib.qa import reconciliation as rc
        from ib.repositories.processed_store import ProcessedStore
        store = ProcessedStore(Path(args.data))
        detail = store.read("revenue_detail")
        rec = store.read("volume_reconciliation")
        sign = store.read("native_sign_check")
        ctrl = store.read("trades_vs_pibcic")
        cov = qf.coverage(detail)
        ok_v, bad_v = rc.gate_volume(rec)
        ok_s, bad_s = rc.gate_sign(sign)
        ok_t, mae = rc.gate_trades_vs_pibcic(ctrl)
        ok_c, bad_c = rc.gate_price_coverage(cov, rc.DEFAULT_MIN_COVERAGE)
        print("PUERTA volumen        :", "PASA" if ok_v else "NO PASA")
        print("PUERTA signo nativo   :", "PASA" if ok_s else "NO PASA")
        print(f"PUERTA TRADES/PIBCIC  : {'PASA' if ok_t else 'NO PASA'}  MAE {mae:.9f} MWh")
        print("PUERTA cobertura      :", "PASA" if ok_c else "NO PASA")
        print("\nCOBERTURA POR MERCADO")
        print(cov.round(1).to_string(index=False))
        if not ok_c:
            print("\nMercados por debajo del minimo:")
            print(bad_c.round(1).to_string(index=False))
        return 0 if (ok_v and ok_s and ok_t) else 1

    if args.cmd == "forecast":
        from ib.engines.forecast_engine import (DEFAULT_SCENARIOS, StorageConfig,
                                                apply_scenario, dispatch_metrics,
                                                optimize_dispatch, storage_from_inputs)
        from ib.repositories.processed_store import ProcessedStore
        store = ProcessedStore(Path(args.data))
        pmd = store.read("pmd")
        if pmd.empty:
            print("No hay serie de precios. Ejecuta antes 'build'.")
            return 2
        pmd["ts"] = pd.to_datetime(pmd["day"]) + pd.to_timedelta((pmd["qh"] - 1) * 15, unit="m")
        s = pmd.groupby(pmd["ts"].dt.floor("h"))["pmd"].mean()
        eff = math.sqrt(args.rte)
        storage = storage_from_inputs(usable_output_mwh=args.mw * args.hours,
                                      turbine_efficiency=eff)
        cfg = StorageConfig(p_turbine_mw=args.mw, p_pump_mw=args.mw,
                            energy_mwh=storage["hydraulic_mwh"], rte=args.rte,
                            eff_turbine=eff, eff_pump=eff)
        prices = apply_scenario(s, DEFAULT_SCENARIOS[args.scenario])
        m = dispatch_metrics(optimize_dispatch(prices, cfg), cfg)
        for k, v in m.items():
            print(f"  {k:28s} {v:,.2f}" if isinstance(v, float) else f"  {k:28s} {v}")
        return 0

    if args.cmd == "purge-raw":
        from ib.repositories.raw_cache import RawCache
        n, gb = RawCache(Path(args.data)).purge_raw()
        print(f"Borrados {n} ficheros raw, liberados {gb:.2f} GB")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
