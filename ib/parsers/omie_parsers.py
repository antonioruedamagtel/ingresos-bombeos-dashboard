"""Parsers de los ficheros públicos de OMIE.

Reglas de signo, todas validadas de forma independiente en la auditoría:
  * PDBC publica signo nativo, generación positiva y bombeo negativo. No se le
    aplica ningún signo adicional por rol de la unidad.
  * PIBCI es un programa incremental y conserva igualmente su signo.
  * En TRADES la energía es cantidad por duración del contrato, y la venta es
    positiva y la compra negativa. PIBCIC es exactamente esa misma energía
    expresada como programa: no deben sumarse las dos.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

_NUM = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _granularity_of(records: list[tuple]) -> tuple[str, float]:
    """Deduce granularidad de un fichero OMIE por su periodo máximo.

    Hallazgo fechado: OMIE pasó el intradiario a cuarto de hora el 19/03/2025,
    manteniendo el diario horario. En los ficheros cuartohorarios el valor
    publicado es POTENCIA en MW, de modo que la energía es valor por 0,25 h.
    En los ficheros horarios el valor ya es energía de la hora. Deducir la
    granularidad por mes, o asumirla, produce un error de factor cuatro.
    """
    mx = max((r[1] for r in records), default=0)
    return ("QH", 0.25) if mx > 25 else ("H", 1.0)


def _f(x: str) -> float:
    s = x.strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def parse_marginal_file(path: Path) -> pd.DataFrame:
    """MARGINALPDBC / MARGINALPIBC: y;m;d;periodo;precio_pt;precio_es;"""
    rows = []
    for ln in Path(path).read_text(encoding="latin-1").splitlines():
        p = ln.strip().split(";")
        if len(p) < 6 or not p[0].isdigit():
            continue
        rows.append((pd.Timestamp(int(p[0]), int(p[1]), int(p[2])), int(p[3]), _f(p[5])))
    return pd.DataFrame(rows, columns=["day", "period", "price"]).drop_duplicates(["day", "period"])


def parse_pdbc_zip(zip_path: Path, ups: set[str]) -> pd.DataFrame:
    """PDBC: y;m;d;periodo;UP;valor;... Programa del mercado diario por unidad."""
    out = []
    with zipfile.ZipFile(zip_path) as z:
        for n in sorted(z.namelist()):
            if not re.search(r"pdbc_\d{8}", n.lower()):
                continue
            recs = []
            for ln in z.read(n).decode("latin-1").splitlines():
                p = ln.split(";")
                if len(p) < 6 or not p[0].isdigit():
                    continue
                recs.append((pd.Timestamp(int(p[0]), int(p[1]), int(p[2])), int(p[3]),
                             p[4].strip().upper(), _f(p[5])))
            if not recs:
                continue
            gran, ph = _granularity_of(recs)
            for d, per, up, v in recs:
                if up in ups:
                    out.append((d, per, up, v * ph, gran))
    return pd.DataFrame(out, columns=["day", "period", "up", "energy_mwh", "granularity"])


def parse_pibci_zip(zip_path: Path, ups: set[str]) -> pd.DataFrame:
    """PIBCI: y;m;d;hora;sesion;UP;energia_incremental;..."""
    out = []
    with zipfile.ZipFile(zip_path) as z:
        for n in sorted(z.namelist()):
            if not re.search(r"pibci_\d{10}", n.lower()):
                continue
            recs = []
            for ln in z.read(n).decode("latin-1").splitlines():
                p = ln.split(";")
                if len(p) < 7 or not p[0].isdigit():
                    continue
                recs.append((pd.Timestamp(int(p[0]), int(p[1]), int(p[2])), int(p[3]),
                             int(p[4]), p[5].strip().upper(), _f(p[6])))
            if not recs:
                continue
            gran, ph = _granularity_of(recs)
            for d, per, ses, up, v in recs:
                if up in ups:
                    out.append((d, per, ses, up, v * ph, gran))
    return pd.DataFrame(out, columns=["day", "period", "session", "up", "energy_mwh", "granularity"])


def parse_pibcic_zip(zip_path: Path, ups: set[str]) -> pd.DataFrame:
    """PIBCIC: programa del intradiario continuo. Control de TRADES, no sumando."""
    out = []
    with zipfile.ZipFile(zip_path) as z:
        for n in sorted(z.namelist()):
            if not re.search(r"pibcic_\d{10}", n.lower()):
                continue
            recs = []
            for ln in z.read(n).decode("latin-1").splitlines():
                p = ln.split(";")
                if len(p) < 7 or not p[0].isdigit():
                    continue
                recs.append((pd.Timestamp(int(p[0]), int(p[1]), int(p[2])), int(p[3]),
                             p[5].strip().upper(), _f(p[6])))
            if not recs:
                continue
            gran, ph = _granularity_of(recs)
            for d, per, up, v in recs:
                if up in ups:
                    out.append((d, per, up, v * ph, gran))
    return pd.DataFrame(out, columns=["day", "period", "up", "energy_mwh", "granularity"])


def parse_trades_zip(zip_path: Path, ups: set[str]) -> pd.DataFrame:
    """TRADES: operaciones del intradiario continuo (XBID).

    energia = cantidad x duracion_del_contrato, venta positiva y compra negativa.
    """
    rows = []
    pat = re.compile(r"(\d{8}) (\d{2}):(\d{2})-(\d{8}) (\d{2}):(\d{2})")
    with zipfile.ZipFile(zip_path) as z:
        for n in sorted(z.namelist()):
            for ln in z.read(n).decode("latin-1").splitlines():
                p = ln.split(";")
                if len(p) < 11 or "/" not in p[0]:
                    continue
                contrato, u_buy, u_sell, price, qty = p[1], p[3].strip().upper(), p[6].strip().upper(), p[8], p[9]
                if u_buy not in ups and u_sell not in ups:
                    continue
                m = pat.match(contrato)
                if not m:
                    continue
                d1, h1, mi1, d2, h2, mi2 = m.groups()
                start = pd.Timestamp(f"{d1[:4]}-{d1[4:6]}-{d1[6:]} {h1}:{mi1}")
                end = pd.Timestamp(f"{d2[:4]}-{d2[4:6]}-{d2[6:]} {h2}:{mi2}")
                dur = (end - start).total_seconds() / 3600.0
                pr, q = _f(price), _f(qty)
                if u_sell in ups:
                    rows.append((u_sell, start, dur, pr, q * dur))
                if u_buy in ups:
                    rows.append((u_buy, start, dur, pr, -q * dur))
    return pd.DataFrame(rows, columns=["up", "start", "duration_h", "price", "energy_mwh"])
