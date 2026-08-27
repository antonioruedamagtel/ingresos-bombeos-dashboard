"""Descargas públicas de OMIE. Sin token, sin certificado, sin API key.

El token del proyecto pertenece a e·sios y nunca debe viajar a OMIE.

Dos hallazgos operativos que este módulo respeta:
  * la nomenclatura de revisión no es siempre `.1`; se prueban revisiones
    sucesivas antes de declarar el fichero ausente;
  * los ficheros mensuales comprimidos se cachean y no se vuelven a descargar
    en cada diagnóstico.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .http import Fetch, build_session, get_bytes

BASE = "https://www.omie.es/es/file-download"
HTML_HINT = b"<html"


def _download(session, parent: str, filename: str, target: Path):
    if target.exists() and target.stat().st_size > 100:
        return Fetch.OK, target
    status, content = get_bytes(session, BASE, params={"parents": parent, "filename": filename},
                                timeout=180, min_bytes=50)
    if status != Fetch.OK:
        return status, None
    if HTML_HINT in content[:400].lower():
        return Fetch.NOT_AVAILABLE_YET, None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return Fetch.OK, target


def download_marginalpdbc(day: date, cache_dir: Path, session=None, revisions=(1, 2, 3)):
    session = session or build_session()
    for rev in revisions:
        t = Path(cache_dir) / "marginalpdbc" / f"{day:%Y%m%d}.{rev}"
        st, p = _download(session, "marginalpdbc", f"marginalpdbc_{day:%Y%m%d}.{rev}", t)
        if st == Fetch.OK:
            return st, p
    return Fetch.NOT_AVAILABLE_YET, None


def download_marginalpibc(day: date, session_no: int, cache_dir: Path, session=None, revisions=(1, 2)):
    session = session or build_session()
    for rev in revisions:
        t = Path(cache_dir) / "marginalpibc" / f"{day:%Y%m%d}_{session_no:02d}.{rev}"
        st, p = _download(session, "marginalpibc",
                          f"marginalpibc_{day:%Y%m%d}{session_no:02d}.{rev}", t)
        if st == Fetch.OK:
            return st, p
    return Fetch.NOT_AVAILABLE_YET, None


def download_monthly_zip(kind: str, yyyymm: str, cache_dir: Path, session=None):
    """kind: pdbc | pdbf | pibci | pibcic | trades"""
    session = session or build_session()
    t = Path(cache_dir) / f"{kind}_{yyyymm}.zip"
    return _download(session, kind, f"{kind}_{yyyymm}.zip", t)
