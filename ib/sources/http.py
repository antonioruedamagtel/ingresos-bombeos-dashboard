"""Cliente HTTP resiliente compartido: retry, backoff, timeout y sesión reutilizable."""
from __future__ import annotations

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class Fetch:
    NOT_AVAILABLE_YET = "NOT_AVAILABLE_YET"
    DOWNLOAD_ERROR = "DOWNLOAD_ERROR"
    OK = "OK"


def build_session(pool: int = 4) -> requests.Session:
    retry = Retry(
        total=4, connect=4, read=4, status=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    s = requests.Session()
    ad = HTTPAdapter(max_retries=retry, pool_connections=pool, pool_maxsize=pool)
    s.mount("https://", ad)
    s.mount("http://", ad)
    s.headers.update({"User-Agent": "ingresos-bombeos/2.0 (analisis privado)"})
    return s


def get_bytes(session: requests.Session, url: str, headers=None, params=None,
              timeout: int = 180, min_bytes: int = 1, attempts: int = 4):
    """Devuelve (status, contenido). Renueva la sesión ante caídas de conexión."""
    last = None
    for i in range(attempts):
        try:
            r = session.get(url, headers=headers, params=params, timeout=timeout)
            if r.status_code == 404:
                return Fetch.NOT_AVAILABLE_YET, b""
            if r.status_code in (401, 403):
                raise RuntimeError(f"Credencial no autorizada (HTTP {r.status_code}) en {url}")
            r.raise_for_status()
            if len(r.content) < min_bytes:
                last = f"respuesta demasiado corta ({len(r.content)} bytes)"
            else:
                return Fetch.OK, r.content
        except requests.exceptions.RequestException as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(min(30.0, 2 ** i))
    return Fetch.DOWNLOAD_ERROR, (last or "").encode()
