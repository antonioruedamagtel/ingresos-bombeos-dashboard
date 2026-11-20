"""Parser I90DIA independiente de la granularidad y del formato.

Soporta simultáneamente:
  * libros .xls históricos (BIFF, vía xlrd) con 37 hojas;
  * libros .xlsx;
  * paquetes CSV modernos (43 ficheros I90DIAnn por día).

Requisitos que cumple, todos verificados contra ficheros reales:
  1. detecta la fila de cabecera de periodos y la fila de nombres meta de forma
     independiente, porque en algunas hojas (I90DIA30) no coinciden;
  2. no asume 24 ni 96 periodos: deduce la granularidad hoja por hoja, porque
     en el mismo libro conviven hojas horarias y cuartohorarias;
  3. filtra por unidad de programación durante el parseo, conservando las filas
     globales o en blanco de las tablas de precio;
  4. conserva el signo nativo publicado, sin reaplicar signos de rol;
  5. devuelve formato largo con la granularidad y la duración del periodo, para
     que el consumidor pueda convertir MW a MWh sin ambigüedad.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from ..util.timeframe import hours_per_period, infer_granularity, periods_to_datetime

LONG_COLUMNS = [
    "datetime", "day", "period", "granularity", "period_hours",
    "sheet", "up", "direction", "concept", "value", "total_declared",
]

_INTERVAL_RE = re.compile(r"^\d{1,2}[AB]?[-:]\d{1,2}[AB]?$")
_CLOCK_RE = re.compile(r"^\d{1,2}:\d{2}[AB]?-\d{1,2}:\d{2}[AB]?$")


def _is_interval_label(x) -> bool:
    s = str(x).strip().upper().replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", "", s)
    return bool(_INTERVAL_RE.match(s) or _CLOCK_RE.match(s))


def _period_number(x) -> int | None:
    s = str(x).strip().upper()
    if _is_interval_label(s):
        return None
    compact = re.sub(r"[^A-Z0-9]", "", s)
    for pat in (r"H(?:ORA)?0?(\d{1,3})", r"PERIODO0?(\d{1,3})", r"P0?(\d{1,3})", r"QH0?(\d{1,3})"):
        m = re.fullmatch(pat, compact)
        if m:
            n = int(m.group(1))
            return n if 1 <= n <= 100 else None
    try:
        f = float(s)
    except ValueError:
        return None
    if float(f).is_integer() and 1 <= f <= 100:
        return int(f)
    return None


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _find_layout(cells: list[list]):
    """Localiza metadatos y periodos sin depender de una columna ``Total``.

    En 2026 REE publicó tres variantes: la histórica con ``Total``, una con el
    separador ``Cuarto de Hora del dia`` y otra sin separador entre metadatos y
    periodos. La frontera inequívoca en esta última es la primera etiqueta de
    intervalo de la fila que contiene la rejilla temporal.
    """
    total_col = period_row = period_start = None
    anchors = {"total", "total mw", "cuarto de hora del dia", "cuarto de hora del día"}
    for r, row in enumerate(cells):
        for c, v in enumerate(row):
            if isinstance(v, str) and v.strip().lower() in anchors:
                total_col, period_row, period_start = c, r, c + 1
                break
        if period_start is not None:
            break

    # Desde enero de 2026 algunas hojas no tienen separador. Se busca la
    # primera columna que inicia una sucesión suficiente de periodos.
    if period_start is None:
        for r, row in enumerate(cells):
            marks = [_is_interval_label(v) or _period_number(v) is not None for v in row]
            if sum(marks) >= 20:
                period_row = r
                period_start = next(i for i, marked in enumerate(marks) if marked)
                total_col = None
                break
    if period_start is None:
        return None

    meta_row = next((
        r for r, row in enumerate(cells)
        if any("unidad de programaci" in str(v).lower() for v in row)
    ), None)
    if meta_row is None:
        meta_row = next((r for r, row in enumerate(cells)
                         if row and isinstance(row[0], str) and row[0].strip()), None)
    if meta_row is None:
        return None
    return meta_row, period_row, total_col, period_start


def _long_from_matrix(cells_all, meta_row, period_row, total_col, period_start, n_cols,
                      sheet, day, selected_ups) -> pd.DataFrame:
    meta_names = []
    for c in range(period_start if total_col is None else total_col):
        v = cells_all[meta_row][c] if c < len(cells_all[meta_row]) else ""
        meta_names.append(str(v).strip())
    labels = [cells_all[period_row][c] if c < len(cells_all[period_row]) else ""
              for c in range(period_start, n_cols)]

    nums = [_period_number(x) for x in labels]
    if sum(1 for x in labels if _is_interval_label(x)) >= 20:
        nums = list(range(1, len(labels) + 1))
    max_p = max([n for n in nums if n], default=0)
    n_labels = sum(1 for n in nums if n)
    gran = infer_granularity(max_p, n_labels)
    ph = hours_per_period(gran)

    up_idx = next((i for i, n in enumerate(meta_names)
                   if "unidad de programaci" in n.lower()), None)
    dir_idx = next((i for i, n in enumerate(meta_names)
                    if n.strip().lower() in {"sentido", "direction"}), None)

    start = max(meta_row, period_row) + 1
    rows = []
    for r in range(start, len(cells_all)):
        row = cells_all[r]
        if not row:
            continue
        meta = [row[c] if c < len(row) else ""
                for c in range(period_start if total_col is None else total_col)]
        if all((isinstance(m, str) and not m.strip()) or m in ("", None) for m in meta):
            continue
        up = str(meta[up_idx]).strip().upper() if up_idx is not None else ""
        if selected_ups is not None and up_idx is not None and up and up not in selected_ups:
            continue
        direction = str(meta[dir_idx]).strip().lower() if dir_idx is not None else ""
        concept_bits = [str(m).strip() for i, m in enumerate(meta)
                        if i != up_idx and str(m).strip() and not _is_number(m)]
        concept = "|".join(concept_bits).lower()
        tot = row[total_col] if total_col is not None and total_col < len(row) else np.nan
        for j, c in enumerate(range(period_start, n_cols)):
            p = nums[j]
            if not p:
                continue
            v = row[c] if c < len(row) else None
            if not _is_number(v) or (isinstance(v, float) and np.isnan(v)):
                continue
            rows.append((p, gran, ph, sheet, up, direction, concept, float(v),
                         float(tot) if _is_number(tot) else np.nan))
    if not rows:
        return pd.DataFrame(columns=LONG_COLUMNS)
    df = pd.DataFrame(rows, columns=["period", "granularity", "period_hours", "sheet",
                                     "up", "direction", "concept", "value", "total_declared"])
    df["day"] = pd.Timestamp(day)
    df["datetime"] = periods_to_datetime(day, df["period"], gran)
    return df.dropna(subset=["datetime"])[LONG_COLUMNS]


def parse_i90_xls(path: Path, day, sheets, selected_ups=None) -> pd.DataFrame:
    import xlrd
    book = xlrd.open_workbook(str(path), on_demand=True)
    frames = []
    available = set(book.sheet_names())
    for name in sheets:
        if name not in available:
            continue
        sh = book.sheet_by_name(name)
        if sh.nrows < 3:
            continue
        head = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(min(sh.nrows, 16))]
        layout = _find_layout(head)
        if layout is None:
            continue
        meta_row, period_row, total_col, period_start = layout
        cells_all = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
        df = _long_from_matrix(cells_all, meta_row, period_row, total_col, period_start, sh.ncols,
                               name, day, selected_ups)
        if not df.empty:
            frames.append(df)
        try:
            book.unload_sheet(name)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=LONG_COLUMNS)


def parse_i90_xlsx(path: Path, day, sheets, selected_ups=None) -> pd.DataFrame:
    book = pd.ExcelFile(path)
    frames = []
    for name in sheets:
        if name not in book.sheet_names:
            continue
        raw = book.parse(sheet_name=name, header=None)
        cells_all = raw.where(pd.notna(raw), "").values.tolist()
        layout = _find_layout(cells_all[:16])
        if layout is None:
            continue
        meta_row, period_row, total_col, period_start = layout
        df = _long_from_matrix(cells_all, meta_row, period_row, total_col, period_start, raw.shape[1],
                               name, day, selected_ups)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=LONG_COLUMNS)


def parse_i90_csv(path: Path, day, sheet_name, selected_ups=None) -> pd.DataFrame:
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return pd.DataFrame(columns=LONG_COLUMNS)
    sep = ";" if text.count(";") >= text.count(",") else ","
    cells_all = []
    num_re = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(\.\d+)?$")
    for ln in text.splitlines():
        conv = []
        for x in ln.split(sep):
            s = x.strip()
            if s and num_re.match(s):
                conv.append(float(s.replace(".", "").replace(",", ".")) if "," in s else float(s))
            else:
                conv.append(s)
        cells_all.append(conv)
    layout = _find_layout(cells_all[:12])
    if layout is None:
        return pd.DataFrame(columns=LONG_COLUMNS)
    meta_row, period_row, total_col, period_start = layout
    n_cols = max(len(r) for r in cells_all)
    return _long_from_matrix(cells_all, meta_row, period_row, total_col, period_start, n_cols,
                             sheet_name, day, selected_ups)


def parse_i90_bundle(paths, day, sheets, selected_ups=None) -> pd.DataFrame:
    frames = []
    wanted = {x.upper() for x in sheets}
    for p in paths:
        p = Path(p)
        s = p.suffix.lower()
        if s == ".xls":
            frames.append(parse_i90_xls(p, day, sheets, selected_ups))
        elif s == ".xlsx":
            frames.append(parse_i90_xlsx(p, day, sheets, selected_ups))
        elif s == ".csv":
            m = re.search(r"(I90DIA\d{2})", p.name.upper())
            name = m.group(1) if m else p.stem.upper()
            if name in wanted:
                frames.append(parse_i90_csv(p, day, name, selected_ups))
    frames = [f for f in frames if f is not None and not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=LONG_COLUMNS)
