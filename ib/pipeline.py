"""Orquestación: fuentes -> parsers -> dominio -> motores -> QA -> analytics.

Todo el cálculo ocurre sobre la rejilla canónica (día, cuarto de hora), que es
unívoca también en los días de 23 y 25 horas.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .domain.aliases import AliasTable
from .engines import afrr_engine as afrr
from .engines import balancing_revenue_engine as bal
from .engines import energy_revenue_engine as ene
from .engines import physical_program_engine as phys
from .parsers.omie_parsers import (parse_marginal_file, parse_pibci_zip,
                                   parse_pibcic_zip, parse_trades_zip)
from .repositories.processed_store import ProcessedStore
from .repositories.raw_cache import RawCache
from .sources import esios_indicators as ind
from .sources import omie_files as omie
from .sources.http import build_session
from .util.grid import attach_datetime, expand
from .util.timeframe import iter_days, month_windows, n_quarters

I90_SHEETS = ["I90DIA02", "I90DIA03", "I90DIA05", "I90DIA06", "I90DIA07", "I90DIA08",
              "I90DIA09", "I90DIA10", "I90DIA11", "I90DIA26", "I90DIA30", "I90DIA36"]
IDA_SESSIONS = range(1, 7)
KEY = ["day", "qh"]


def load_assets(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for c in ("up_generation", "up_pumping"):
        df[c] = df[c].astype(str).str.strip().str.upper()
    for c in df.columns:
        if c.startswith(("mw_", "potencia_", "almacen", "efic", "band_", "round_")):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _marginal_to_grid(path, day, value_name="price") -> pd.DataFrame:
    m = parse_marginal_file(path)
    m = m[m["day"] == pd.Timestamp(day)]
    if m.empty:
        return pd.DataFrame(columns=["day", "qh", value_name])
    m = m.rename(columns={"price": value_name})
    m["granularity"] = "H" if m["period"].max() <= 25 else "QH"
    g = expand(m, "P", value_col=value_name)
    return g[["day", "qh", value_name]]


class Pipeline:
    def __init__(self, root: Path, assets_path: Path, token: str | None = None):
        self.root = Path(root)
        self.assets = load_assets(assets_path)
        self.aliases = AliasTable.from_assets(self.assets)
        self.token = token or os.getenv("ESIOS_API_KEY")
        self.session = build_session()
        self.cache = RawCache(self.root)
        self.store = ProcessedStore(self.root)
        self.omie_dir = self.root / "raw" / "omie"
        self.ind_dir = self.root / "normalized" / "esios"

    # ---------------------------------------------------------------- ingesta
    def ingest_i90(self, start: date, end: date, log=print) -> pd.DataFrame:
        ups = self.aliases.codes()
        rows = []
        for d in iter_days(start, end):
            st = self.cache.ensure_day(d, I90_SHEETS, ups, token=self.token, session=self.session)
            rows.append({"day": d, "status": st})
            if st not in ("OK", "CACHED"):
                log(f"{d}: {st}")
        return pd.DataFrame(rows)

    def pmd(self, start: date, end: date) -> pd.DataFrame:
        out = []
        for d in iter_days(start, end):
            st, p = omie.download_marginalpdbc(d, self.omie_dir, session=self.session)
            if p is None:
                continue
            out.append(_marginal_to_grid(p, d, "pmd"))
        return (pd.concat(out, ignore_index=True).drop_duplicates(KEY)
                if out else pd.DataFrame(columns=["day", "qh", "pmd"]))

    def ida_prices(self, start: date, end: date) -> pd.DataFrame:
        out = []
        for d in iter_days(start, end):
            for s in IDA_SESSIONS:
                st, p = omie.download_marginalpibc(d, s, self.omie_dir, session=self.session)
                if p is None:
                    continue
                g = _marginal_to_grid(p, d, "price")
                if g.empty:
                    continue
                g["session"] = s
                out.append(g)
        return (pd.concat(out, ignore_index=True).drop_duplicates(KEY + ["session"])
                if out else pd.DataFrame(columns=["day", "qh", "session", "price"]))

    def omie_programs(self, start: date, end: date):
        ups = self.aliases.codes()
        pib_l, trd_l, pic_l = [], [], []
        for ym in month_windows(start, end):
            st, p = omie.download_monthly_zip("pibci", ym, self.omie_dir, session=self.session)
            if p:
                pib_l.append(parse_pibci_zip(p, ups))
            st, p = omie.download_monthly_zip("trades", ym, self.omie_dir, session=self.session)
            if p:
                trd_l.append(parse_trades_zip(p, ups))
            st, p = omie.download_monthly_zip("pibcic", ym, self.omie_dir, session=self.session)
            if p:
                pic_l.append(parse_pibcic_zip(p, ups))
        pib = pd.concat(pib_l, ignore_index=True) if pib_l else pd.DataFrame()
        trd = pd.concat(trd_l, ignore_index=True) if trd_l else pd.DataFrame()
        pic = pd.concat(pic_l, ignore_index=True) if pic_l else pd.DataFrame()
        lo, hi = pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1)
        if not pib.empty:
            pib["granularity"] = "H" if pib["period"].max() <= 25 else "QH"
            pib = expand(pib, "E", value_col="energy_mwh")
            pib = pib[(pib["day"] >= lo) & (pib["day"] < hi)]
        if not pic.empty:
            pic["granularity"] = "H" if pic["period"].max() <= 25 else "QH"
            pic = expand(pic, "E", value_col="energy_mwh")
            pic = pic[(pic["day"] >= lo) & (pic["day"] < hi)]
        if not trd.empty:
            trd = trd[(trd["start"] >= lo) & (trd["start"] < hi)].copy()
            trd["day"] = trd["start"].dt.normalize()
            trd["period"] = trd["start"].dt.hour + 1
            trd["granularity"] = "H"
            trd = expand(trd, "E", value_col="energy_mwh")
        return pib, trd, pic

    # ---------------------------------------------------------------- cálculo
    def build(self, start: date, end: date, log=print) -> dict:
        i90 = self.cache.load_range(start, end)
        if i90.empty:
            raise RuntimeError("No hay caché I90 para el periodo. Ejecuta antes ingest_i90.")
        pmd = self.pmd(start, end)
        idap = self.ida_prices(start, end)
        pib, trd, pic = self.omie_programs(start, end)

        p48 = phys.p48(i90)
        pbf = phys.pbf(i90)
        sign_check = phys.check_native_sign(i90, self.aliases)

        rt = bal.split_daily_restrictions(i90)
        rtr = bal.split_real_time(i90)
        energy_raw = {
            "RT_DIARIO": rt["RT_DIARIO"], "REEQUILIBRIO": rt["REEQUILIBRIO"],
            "RT_TIEMPO_REAL": rtr["RT_TIEMPO_REAL"], "DESVIOS_RT": rtr["DESVIOS_RT"],
            "RR": i90[i90["sheet"] == "I90DIA06"], "MFRR": i90[i90["sheet"] == "I90DIA07"],
        }
        price_raw = {
            "RT_DIARIO": "I90DIA09", "REEQUILIBRIO": "I90DIA09",
            "RT_TIEMPO_REAL": "I90DIA10", "DESVIOS_RT": "I90DIA10",
            "RR": "I90DIA11", "MFRR": "I90DIA30",
        }
        energy_grid = {k: (expand(v, "E") if v is not None and not v.empty else v)
                       for k, v in energy_raw.items()}
        price_grid = {k: expand(i90[i90["sheet"] == sh], "P") for k, sh in price_raw.items()}

        comps = [ene.day_ahead_base(p48, pmd, self.aliases)]
        if not pib.empty:
            comps.append(ene.intraday_auction(pib, idap, pmd, self.aliases))
        if not trd.empty:
            comps.append(ene.intraday_continuous(trd, pmd, self.aliases))
        for mkt, e in energy_grid.items():
            if e is None or e.empty:
                continue
            comps.append(bal.value_market(e, price_grid[mkt], mkt, pmd, self.aliases))

        band_price = ind.band_price_series(start, end, token=self.token, session=self.session,
                                           cache_dir=self.ind_dir)
        if not band_price.empty:
            comps.append(afrr.band_revenue(i90, band_price, self.aliases))
        sys_sec = ind.system_secondary_net(start, end, token=self.token, session=self.session,
                                           cache_dir=self.ind_dir)
        if not sys_sec.empty:
            comps.append(afrr.secondary_energy_net_estimate(i90, sys_sec, self.aliases))

        detail = pd.concat([c for c in comps if c is not None and not c.empty], ignore_index=True)
        detail = detail[detail["asset"].notna()].copy()

        deltas = {}
        if not pib.empty:
            deltas["IDA"] = pib[KEY + ["up", "energy_mwh"]]
        if not trd.empty:
            deltas["MIC"] = trd[KEY + ["up", "energy_mwh"]]
        for mkt, e in energy_grid.items():
            if e is None or e.empty:
                continue
            deltas[mkt] = e.rename(columns={"value": "energy_mwh"})[KEY + ["up", "energy_mwh"]]
        rec = phys.reconcile(p48, pbf, deltas, alias_table=self.aliases, level="asset")
        rec_sum = phys.reconciliation_summary(rec)

        control = pd.DataFrame()
        if not trd.empty and not pic.empty:
            a = trd.groupby(KEY + ["up"], as_index=False)["energy_mwh"].sum().rename(
                columns={"energy_mwh": "trades"})
            b = pic.groupby(KEY + ["up"], as_index=False)["energy_mwh"].sum().rename(
                columns={"energy_mwh": "pibcic"})
            control = a.merge(b, on=KEY + ["up"], how="outer").fillna(0.0)
            control["abs_error"] = (control["trades"] - control["pibcic"]).abs()

        self.store.write("pmd", pmd)
        if not sys_sec.empty:
            self.store.write("system_secondary_net", sys_sec)
        self.store.write("revenue_detail", detail)
        self.store.write("volume_reconciliation", rec_sum)
        self.store.write("native_sign_check", sign_check)
        if not control.empty:
            self.store.write("trades_vs_pibcic", control)
        return {"detail": detail, "reconciliation": rec_sum, "sign_check": sign_check,
                "trades_vs_pibcic": control, "pmd": pmd, "p48": p48, "pbf": pbf, "i90": i90}


def summarize(detail: pd.DataFrame, assets: pd.DataFrame, mw_col: str = "mw_reference") -> pd.DataFrame:
    d = detail.copy()
    d["month"] = pd.to_datetime(d["datetime"]).dt.to_period("M").dt.to_timestamp()
    g = d.groupby(["asset", "month", "market"], as_index=False).agg(
        revenue=("revenue_incremental", "sum"),
        revenue_gross=("revenue_gross", "sum"),
        quantity=("quantity", "sum"),
        rows=("quantity", "size"),
        observed=("data_class", lambda s: (s == "OBSERVADO").mean()),
    )
    return g.merge(assets[["asset", mw_col]], on="asset", how="left")


def captured_prices(detail: pd.DataFrame, aliases) -> pd.DataFrame:
    """Precio capturado por activo y rol, excluyendo remuneración de capacidad."""
    d = detail[detail["market"] != "AFRR_BANDA"].copy()
    d["role"] = d["up"].map(lambda u: aliases.role_of(u))
    p48 = detail[detail["market"] == "DA"].copy()
    p48["role"] = p48["up"].map(lambda u: aliases.role_of(u))
    vol = p48.groupby(["asset", "role"], as_index=False)["quantity"].sum().rename(
        columns={"quantity": "p48_mwh"})
    rev = d.groupby(["asset", "role"], as_index=False)["revenue_incremental"].sum().rename(
        columns={"revenue_incremental": "revenue"})
    out = vol.merge(rev, on=["asset", "role"], how="outer")
    out["precio_capturado"] = out["revenue"] / out["p48_mwh"].replace(0, np.nan)
    return out
