"""Regresion dorada del puente de ingresos, Aguayo enero de 2023.

Se ejecuta sin red, sobre las cachés incluidas en tests/data.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from ib.engines import balancing_revenue_engine as bal
from ib.engines import energy_revenue_engine as ene
from ib.engines import physical_program_engine as phys
from ib.parsers.omie_parsers import parse_marginal_file, parse_pibci_zip, parse_trades_zip
from ib.util.grid import expand
from ib.util.timeframe import iter_days

DATA = Path(__file__).resolve().parent / "data"
START, END = date(2023, 1, 1), date(2023, 1, 31)


def _grid(path, day, name):
    from ib.pipeline import _marginal_to_grid
    return _marginal_to_grid(path, day, name)


@pytest.fixture(scope="module")
def components(request):
    i90 = pd.concat([pd.read_parquet(p) for p in
                     sorted((DATA / "i90" / "2023" / "01").glob("*.parquet"))], ignore_index=True)
    from ib.domain.aliases import AliasTable
    from ib.pipeline import load_assets
    assets = load_assets(Path(__file__).resolve().parents[1] / "config" / "assets.csv")
    aliases = AliasTable.from_assets(assets)
    ups = aliases.codes()

    pmd = pd.concat([_grid(DATA / "omie" / "marginalpdbc" / f"{d:%Y%m%d}.1", d, "pmd")
                     for d in iter_days(START, END)
                     if (DATA / "omie" / "marginalpdbc" / f"{d:%Y%m%d}.1").exists()],
                    ignore_index=True).drop_duplicates(["day", "qh"])
    idap = []
    for d in iter_days(START, END):
        for s in range(1, 7):
            f = DATA / "omie" / "marginalpibc" / f"{d:%Y%m%d}_{s:02d}.1"
            if f.exists():
                g = _grid(f, d, "price")
                g["session"] = s
                idap.append(g)
    idap = pd.concat(idap, ignore_index=True).drop_duplicates(["day", "qh", "session"])

    pib = parse_pibci_zip(DATA / "omie" / "pibci_202301.zip", ups)
    pib["granularity"] = "H"
    pib = expand(pib, "E", value_col="energy_mwh")
    pib = pib[(pib["day"] >= pd.Timestamp(START)) & (pib["day"] <= pd.Timestamp(END))]

    trd = parse_trades_zip(DATA / "omie" / "trades_202301.zip", ups)
    trd = trd[(trd["start"] >= pd.Timestamp(START)) & (trd["start"] < pd.Timestamp(END) + pd.Timedelta(days=1))].copy()
    trd["day"] = trd["start"].dt.normalize()
    trd["period"] = trd["start"].dt.hour + 1
    trd["granularity"] = "H"
    trd = expand(trd, "E", value_col="energy_mwh")

    p48, pbf = phys.p48(i90), phys.pbf(i90)
    rt, rtr = bal.split_daily_restrictions(i90), bal.split_real_time(i90)
    energy = {"RT_DIARIO": rt["RT_DIARIO"], "REEQUILIBRIO": rt["REEQUILIBRIO"],
              "RT_TIEMPO_REAL": rtr["RT_TIEMPO_REAL"], "DESVIOS_RT": rtr["DESVIOS_RT"],
              "RR": i90[i90["sheet"] == "I90DIA06"], "MFRR": i90[i90["sheet"] == "I90DIA07"]}
    prices = {"RT_DIARIO": "I90DIA09", "REEQUILIBRIO": "I90DIA09",
              "RT_TIEMPO_REAL": "I90DIA10", "DESVIOS_RT": "I90DIA10",
              "RR": "I90DIA11", "MFRR": "I90DIA30"}
    eg = {k: expand(v, "E") for k, v in energy.items() if not v.empty}
    pg = {k: expand(i90[i90["sheet"] == sh], "P") for k, sh in prices.items()}

    comps = [ene.day_ahead_base(p48, pmd, aliases),
             ene.intraday_auction(pib, idap, pmd, aliases),
             ene.intraday_continuous(trd, pmd, aliases)]
    for k, e in eg.items():
        comps.append(bal.value_market(e, pg[k], k, pmd, aliases))
    detail = pd.concat(comps, ignore_index=True)
    detail = detail[detail["asset"].notna()]

    deltas = {"IDA": pib[["day", "qh", "up", "energy_mwh"]],
              "MIC": trd[["day", "qh", "up", "energy_mwh"]]}
    for k, e in eg.items():
        deltas[k] = e.rename(columns={"value": "energy_mwh"})[["day", "qh", "up", "energy_mwh"]]
    rec = phys.reconciliation_summary(
        phys.reconcile(p48, pbf, deltas, alias_table=aliases, level="asset"))
    return {"detail": detail, "rec": rec, "aliases": aliases}


def test_cierre_de_volumenes_de_toda_la_flota(components):
    rec = components["rec"]
    assert rec["closes"].all(), rec[~rec["closes"]].to_string()
    assert rec["residual"].abs().max() < 1.0


def test_precios_capturados_de_aguayo(components):
    d = components["detail"]
    d = d[(d["asset"] == "Aguayo") & (d["market"] != "AFRR_BANDA")]
    p48 = d[d["market"] == "DA"].groupby("up")["quantity"].sum()
    gen = d[d["up"] == "AGUG"]["revenue_incremental"].sum() / p48["AGUG"]
    bom = -d[d["up"] == "AGUB"]["revenue_incremental"].sum() / -p48["AGUB"]
    assert abs(gen - 106.11) < 0.5      # benchmark externo 115,95
    assert abs(bom - 21.86) < 0.5       # benchmark externo 22,12


def test_regresiones_al_euro_frente_al_motor_anterior(components):
    """Los dos componentes que el motor anterior ya calculaba bien."""
    d = components["detail"]
    ag = d[d["asset"] == "Aguayo"]
    rt = ag[ag["market"].isin(["RT_DIARIO", "REEQUILIBRIO"])]["revenue_incremental"].sum()
    mf = ag[ag["market"] == "MFRR"]["revenue_incremental"].sum()
    assert abs(rt - 765_402) < 500
    assert abs(mf - 600_437) < 500


def test_saldo_y_residuo_frente_al_benchmark(components):
    d = components["detail"]
    ag = d[(d["asset"] == "Aguayo") & (d["market"] != "AFRR_BANDA")]
    saldo = ag["revenue_incremental"].sum()
    assert abs(saldo - 4_368_387) < 5_000
    # el residuo frente al benchmark externo se publica, no se ajusta
    residuo = 5_081_706 - saldo
    assert 0 < residuo < 900_000
