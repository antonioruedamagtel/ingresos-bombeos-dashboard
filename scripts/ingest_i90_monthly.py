"""Ingesta eficiente del I90 solicitando un paquete mensual a e·sios.

El endpoint devuelve un ZIP exterior con un ZIP por día. Cada paquete diario
se procesa con la misma caché compacta y las mismas validaciones que la CLI.
La credencial se lee de ``.env`` y nunca se incorpora a los ficheros de datos.
"""
from __future__ import annotations

import argparse
import gc
import io
import os
import re
import sys
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ib.pipeline import I90_SHEETS, load_assets
from ib.domain.aliases import AliasTable
from ib.repositories.raw_cache import RawCache
from ib.sources.esios_archive import API_BASE, I90_ARCHIVE_ID, _persist, headers
from ib.sources.http import Fetch, build_session, get_bytes
from ib.util.timeframe import iter_days


DATE_IN_NAME = re.compile(r"(\d{8})")


def month_ranges(start: date, end: date):
    for period in pd.period_range(start, end, freq="M"):
        first = max(start, period.start_time.date())
        last = min(end, period.end_time.date())
        yield period.strftime("%Y-%m"), first, last


def ingest_month(cache: RawCache, first: date, last: date, sheets, ups, token: str) -> Counter:
    missing = [day for day in iter_days(first, last) if not cache.has(day)]
    if not missing:
        return Counter(CACHED=(last - first).days + 1)

    params = {
        "date_type": "datos",
        "locale": "es",
        "start_date": f"{first.isoformat()}T00:00:00+00:00",
        "end_date": f"{last.isoformat()}T23:59:59+00:00",
    }
    status, content = get_bytes(
        build_session(),
        f"{API_BASE}/archives/{I90_ARCHIVE_ID}/download",
        headers=headers(token),
        params=params,
        min_bytes=5_000,
    )
    if status != Fetch.OK:
        return Counter({str(status): len(missing)})

    counts: Counter = Counter()
    expected = set(missing)
    with zipfile.ZipFile(io.BytesIO(content)) as outer:
        for member in outer.namelist():
            match = DATE_IN_NAME.search(Path(member).name)
            if not match:
                continue
            day = date.fromisoformat(
                f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
            )
            if day not in expected:
                continue
            daily_content = outer.read(member)
            try:
                _persist(daily_content, cache.raw, day)
                counts[cache.ensure_day(day, sheets, ups, token=token)] += 1
            finally:
                # Algunos XLS antiguos mantienen el handle abierto hasta que
                # el lector es recolectado en Windows. La copia RAW es siempre
                # regenerable; la caché parquet ya ha sido verificada antes.
                gc.collect()
                cache.purge_raw()
            expected.remove(day)

    if expected:
        counts["MISSING_FROM_ARCHIVE"] += len(expected)
    counts["CACHED"] += (last - first).days + 1 - len(missing)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--data", default=str(ROOT / "data"))
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = (os.getenv("ESIOS_API_KEY") or "").strip()
    if not token:
        raise RuntimeError("Falta ESIOS_API_KEY en .env")

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    assets = load_assets(ROOT / "config" / "assets.csv")
    ups = AliasTable.from_assets(assets).codes()
    cache = RawCache(Path(args.data))
    total: Counter = Counter()

    for label, first, last in month_ranges(start, end):
        counts = ingest_month(cache, first, last, I90_SHEETS, ups, token)
        total.update(counts)
        print(f"{label}: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())), flush=True)

    print("TOTAL: " + ", ".join(f"{key}={value}" for key, value in sorted(total.items())))
    failures = sum(value for key, value in total.items() if key not in {"OK", "CACHED", "NO_UNIT_DATA_PUBLISHED"})
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
