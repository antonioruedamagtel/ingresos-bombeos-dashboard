"""Construye por meses el histórico agregado de la demo pública.

La ejecución por ventanas evita mantener varios millones de filas en memoria.
Los ficheros de precios de OMIE se precargan en paralelo, el cálculo mensual
usa el motor productivo y solo se conservan piezas agregadas reanudables.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ib.pipeline import Pipeline
from ib.qa import quality_flags as qf
from ib.qa import reconciliation as rc
from ib.sources import omie_files as omie
from ib.sources.http import Fetch, build_session
from ib.ui.theme import MARKET_GROUPS


PARTS = ROOT / "data" / "demo_parts"
_THREAD_LOCAL = threading.local()


def month_ranges(start: date, end: date):
    for period in pd.period_range(start, end, freq="M"):
        first = max(start, period.start_time.date())
        last = min(end, period.end_time.date())
        yield period.strftime("%Y-%m"), first, last


def session():
    if not hasattr(_THREAD_LOCAL, "session"):
        _THREAD_LOCAL.session = build_session()
    return _THREAD_LOCAL.session


def prefetch_prices(first: date, last: date, cache_dir: Path, workers: int) -> dict:
    tasks = []
    for day in pd.date_range(first, last, freq="D"):
        market_day = day.date()
        tasks.append(("DA", market_day, None))
        tasks.extend(("IDA", market_day, number) for number in range(1, 7))

    def fetch(task):
        kind, market_day, number = task
        if kind == "DA":
            status, _ = omie.download_marginalpdbc(market_day, cache_dir, session=session())
        else:
            status, _ = omie.download_marginalpibc(market_day, number, cache_dir, session=session())
        return kind, status

    counts = {"DA_OK": 0, "IDA_OK": 0, "missing": 0}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fetch, task) for task in tasks]
        for future in as_completed(futures):
            kind, status = future.result()
            if status == Fetch.OK:
                counts[f"{kind}_OK"] += 1
            else:
                counts["missing"] += 1
    return counts


def aggregate_month(result: dict, label: str, output: Path) -> dict:
    detail = result["detail"].copy()
    detail["datetime"] = pd.to_datetime(detail["datetime"])
    detail["month"] = label
    detail["role"] = detail["up"].map(result_aliases.role_of).fillna("unknown")
    detail["market_group"] = detail["market"].map(MARKET_GROUPS).fillna("Otros")
    detail["observed_rows"] = (detail["data_class"] == "OBSERVADO").astype(int)
    detail["estimated_revenue"] = np.where(
        detail["data_class"] == "ESTIMADO", detail["revenue_incremental"], 0.0
    )
    monthly = detail.groupby(
        ["month", "asset", "market", "market_group", "role"], as_index=False
    ).agg(
        revenue=("revenue_incremental", "sum"), quantity=("quantity", "sum"),
        rows=("quantity", "size"), observed_rows=("observed_rows", "sum"),
        estimated_revenue=("estimated_revenue", "sum"),
    )

    pmd = result["pmd"].copy()
    pmd["day"] = pd.to_datetime(pmd["day"])
    pmd["datetime"] = pmd["day"] + pd.to_timedelta((pmd["qh"] - 1) * 15, unit="m")
    prices = pmd.set_index("datetime")["pmd"].resample("1h").mean().rename("price").reset_index()
    coverage = qf.coverage(detail)
    reconciliation = result["reconciliation"].copy()

    output.mkdir(parents=True, exist_ok=True)
    monthly.to_parquet(output / "monthly.parquet", index=False)
    prices.to_parquet(output / "prices.parquet", index=False)
    coverage.to_parquet(output / "coverage.parquet", index=False)
    reconciliation.to_parquet(output / "reconciliation.parquet", index=False)

    ok_v, _ = rc.gate_volume(reconciliation)
    ok_s, _ = rc.gate_sign(result["sign_check"])
    ok_t, mae = rc.gate_trades_vs_pibcic(result["trades_vs_pibcic"])
    ok_c, bad_c = rc.gate_price_coverage(coverage, rc.DEFAULT_MIN_COVERAGE)
    metadata = {
        "month": label, "detail_rows": int(len(detail)),
        "assets": int(detail["asset"].nunique()),
        "total_revenue_eur": float(detail["revenue_incremental"].sum()),
        "observed_rows": int((detail["data_class"] == "OBSERVADO").sum()),
        "qa": {"volume": ok_v, "sign": ok_s, "trades": ok_t, "coverage": ok_c,
               "trades_mae_mwh": mae, "low_coverage_markets": bad_c["market"].tolist()},
    }
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def clean_omie_cache(current_label: str, cache_dir: Path) -> tuple[int, int]:
    """Borra solo descargas OMIE regenerables que ya están agregadas."""
    deleted, bytes_deleted = 0, 0
    resolved_root = cache_dir.resolve()
    for path in cache_dir.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved_root not in resolved.parents:
            raise RuntimeError(f"Ruta de caché fuera del ámbito previsto: {resolved}")
        digits = "".join(char for char in path.name if char.isdigit())
        file_month = digits[:6] if len(digits) >= 6 else ""
        if path.parent.name == "marginalpdbc" and file_month == "202301":
            # Muestra mínima versionada que permite abrir el dashboard local.
            continue
        current_month = current_label.replace("-", "")
        # Los ZIP mensuales del mes actual se reutilizan como mes previo en la
        # siguiente ventana; los precios diarios ya no son necesarios.
        remove = file_month < current_month if path.parent == cache_dir else file_month <= current_month
        if file_month and remove:
            size = path.stat().st_size
            path.unlink()
            deleted += 1
            bytes_deleted += size
    return deleted, bytes_deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--data", default=str(ROOT / "data"))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    pipeline = Pipeline(Path(args.data), ROOT / "config" / "assets.csv")
    global result_aliases
    result_aliases = pipeline.aliases

    failures = []
    for label, first, last in month_ranges(start, end):
        output = PARTS / label
        marker = output / "metadata.json"
        if marker.exists():
            print(f"{label}: CACHED", flush=True)
            continue
        missing_i90 = [day.date() for day in pd.date_range(first, last) if not pipeline.cache.has(day.date())]
        if missing_i90:
            print(f"{label}: pendiente I90 ({len(missing_i90)} días)", flush=True)
            failures.append(label)
            continue
        prefetched = prefetch_prices(first, last, pipeline.omie_dir, max(1, args.workers))
        print(f"{label}: OMIE DA={prefetched['DA_OK']} IDA={prefetched['IDA_OK']} ausentes={prefetched['missing']}", flush=True)
        result = pipeline.build(first, last, log=lambda message: print(f"{label}: {message}", flush=True))
        metadata = aggregate_month(result, label, output)
        deleted, bytes_deleted = clean_omie_cache(label, pipeline.omie_dir)
        qa = metadata["qa"]
        print(
            f"{label}: filas={metadata['detail_rows']:,} activos={metadata['assets']} "
            f"QA V/S/T/C={int(qa['volume'])}/{int(qa['sign'])}/{int(qa['trades'])}/{int(qa['coverage'])} "
            f"raw_borrado={deleted} ({bytes_deleted / 1024**2:.1f} MB)", flush=True,
        )
        if not (qa["volume"] and qa["sign"] and qa["trades"]):
            failures.append(label)

    if failures:
        print("MESES PENDIENTES O CON PUERTA CRÍTICA: " + ", ".join(sorted(set(failures))))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
