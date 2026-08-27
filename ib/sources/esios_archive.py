"""Descarga del archivo I90DIA (archive id 34) de e·sios.

Contrato:
  * autenticación por cabecera x-api-key, exclusiva de e·sios;
  * un día ausente no es un error: se marca NOT_AVAILABLE_YET, porque el I90
    se publica con unos noventa días de retraso;
  * el contenido puede ser ZIP con un libro, XLSX directo, XLS binario o un
    paquete de CSV. Los cuatro casos se resuelven aquí.
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import date
from pathlib import Path

from .http import Fetch, build_session, get_bytes

I90_ARCHIVE_ID = 34
API_BASE = "https://api.esios.ree.es"


def headers(token: str | None = None) -> dict:
    token = (token or os.getenv("ESIOS_API_KEY") or "").strip()
    if not token:
        raise RuntimeError("Falta ESIOS_API_KEY. e·sios exige clave personal; OMIE no usa token.")
    return {
        "Accept": "application/json; application/vnd.esios-api-v1+json",
        "Content-Type": "application/json",
        "x-api-key": token,
    }


def _persist(content: bytes, raw_dir: Path, day: date) -> list[Path]:
    ymd = day.strftime("%Y%m%d")
    raw_dir.mkdir(parents=True, exist_ok=True)
    bio = io.BytesIO(content)
    if zipfile.is_zipfile(bio):
        bio.seek(0)
        with zipfile.ZipFile(bio) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            if "[Content_Types].xml" in names and any(n.startswith("xl/") for n in names):
                t = raw_dir / f"I90DIA_{ymd}.xlsx"
                t.write_bytes(content)
                return [t]
            saved = []
            for n in names:
                base = Path(n).name
                if not base.lower().endswith((".xls", ".xlsx", ".csv")):
                    continue
                t = raw_dir / base
                t.write_bytes(zf.read(n))
                saved.append(t)
            if saved:
                return saved
    if content[:8] == bytes.fromhex("D0CF11E0A1B11AE1"):
        t = raw_dir / f"I90DIA_{ymd}.xls"
        t.write_bytes(content)
        return [t]
    head = content[:400].decode("utf-8", errors="ignore").lower()
    if ";" in head or "," in head:
        t = raw_dir / f"I90DIA_{ymd}.csv"
        t.write_bytes(content)
        return [t]
    raise RuntimeError(f"Formato de descarga I90 no reconocido para {day} ({len(content)} bytes)")


def download_day(day: date, raw_dir: Path, token: str | None = None, session=None):
    """Devuelve (status, rutas). Reutiliza el raw si ya está presente."""
    raw_dir = Path(raw_dir)
    ymd = day.strftime("%Y%m%d")
    existing = [p for p in raw_dir.glob(f"*{ymd}*")
                if p.is_file() and p.suffix.lower() in {".xls", ".xlsx", ".csv"} and p.stat().st_size > 0]
    if existing:
        return Fetch.OK, sorted(existing)
    session = session or build_session()
    url = f"{API_BASE}/archives/{I90_ARCHIVE_ID}/download"
    params = {
        "date_type": "datos",
        "locale": "es",
        "start_date": f"{day.isoformat()}T00:00:00+00:00",
        "end_date": f"{day.isoformat()}T23:59:59+00:00",
    }
    status, content = get_bytes(session, url, headers=headers(token), params=params, min_bytes=5000)
    if status != Fetch.OK:
        return status, []
    return Fetch.OK, _persist(content, raw_dir, day)
