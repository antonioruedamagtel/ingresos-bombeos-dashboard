"""Capa RAW y caché compacta diaria, con política LOW-DISK.

Patrón obligatorio: descargar un día, parsear sólo las tablas necesarias,
escribir caché compacta, verificar la caché y sólo entonces borrar el raw.
Nunca se escribe un checkpoint vacío para un día que falló: ese día sigue
pendiente y se reanuda en la siguiente ejecución.
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from ..parsers.i90_parser import parse_i90_bundle
from ..sources.esios_archive import download_day
from ..sources.http import Fetch


class RawCache:
    def __init__(self, root: Path, max_raw_gb: float = 2.0):
        self.root = Path(root)
        self.raw = self.root / "raw" / "i90"
        self.compact = self.root / "normalized" / "i90"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.compact.mkdir(parents=True, exist_ok=True)
        self.max_raw_gb = max_raw_gb

    def raw_gb(self) -> float:
        return sum(p.stat().st_size for p in self.raw.rglob("*") if p.is_file()) / 1024 ** 3

    def compact_path(self, day: date) -> Path:
        return self.compact / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y%m%d}.parquet"

    def has(self, day: date) -> bool:
        return self.compact_path(day).exists()

    def load(self, day: date) -> pd.DataFrame:
        p = self.compact_path(day)
        return pd.read_parquet(p) if p.exists() else pd.DataFrame()

    def ensure_day(self, day: date, sheets, selected_ups, token=None, session=None,
                   keep_raw: bool = False) -> str:
        if self.has(day):
            return "CACHED"
        status, paths = download_day(day, self.raw, token=token, session=session)
        if status != Fetch.OK or not paths:
            return status
        try:
            df = parse_i90_bundle(paths, day, sheets, selected_ups)
        except Exception as exc:                                    # noqa: BLE001
            return f"PARSE_ERROR: {exc}"
        if df.empty:
            # El fichero existe y se descarga bien, pero no publica datos por
            # unidad de programacion. Ocurrio el 29/04/2025, el dia siguiente al
            # apagon, cuando el I90DIA02 solo trae unidades de interconexion.
            # No es un fallo de descarga ni de parseo: es un dia sin publicacion
            # por unidad y debe verse como tal en el control de calidad.
            out = self.compact_path(day)
            out.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(columns=["datetime", "day", "period", "granularity",
                                  "period_hours", "sheet", "up", "direction",
                                  "concept", "value", "total_declared"]).to_parquet(out, index=False)
            if not keep_raw:
                for p_ in paths:
                    try:
                        Path(p_).unlink(missing_ok=True)
                    except Exception:                                # noqa: BLE001
                        pass
            return "NO_UNIT_DATA_PUBLISHED"
        out = self.compact_path(day)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        # Verificar la caché antes de tocar el raw.
        try:
            check = pd.read_parquet(out)
            ok = len(check) == len(df)
        except Exception:                                            # noqa: BLE001
            ok = False
        if ok and not keep_raw:
            for p in paths:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:                                    # noqa: BLE001
                    pass
        return "OK" if ok else "CACHE_VERIFY_ERROR"

    def load_range(self, start: date, end: date) -> pd.DataFrame:
        frames = []
        d = start
        while d <= end:
            p = self.compact_path(d)
            if p.exists():
                frames.append(pd.read_parquet(p))
            d = d.fromordinal(d.toordinal() + 1)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def purge_raw(self) -> tuple[int, float]:
        n, b = 0, 0
        for p in list(self.raw.rglob("*")):
            if p.is_file():
                b += p.stat().st_size
                p.unlink(missing_ok=True)
                n += 1
        return n, b / 1024 ** 3
