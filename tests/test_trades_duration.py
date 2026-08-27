"""Regresion dorada: TRADES por duracion reproduce PIBCIC con error nulo."""
from pathlib import Path

import pandas as pd

from ib.parsers.omie_parsers import parse_pibcic_zip, parse_trades_zip
from ib.util.grid import expand

DATA = Path(__file__).resolve().parent / "data" / "omie"
UPS = {"AGUG", "AGUB", "MUEL", "MUEB", "SLTG", "SLTB", "TJEG", "TJEB",
       "MLTG", "MLTB", "GUIG", "GUIB", "IPG", "IPB", "UFBG", "UFBB"}


def test_trades_igual_pibcic():
    tr = parse_trades_zip(DATA / "trades_202301.zip", UPS)
    pic = parse_pibcic_zip(DATA / "pibcic_202301.zip", UPS)
    tr = tr[tr["start"] < pd.Timestamp("2023-02-01")].copy()
    tr["day"] = tr["start"].dt.normalize()
    tr["period"] = tr["start"].dt.hour + 1
    tr["granularity"] = "H"
    tr = expand(tr, "E", value_col="energy_mwh")
    pic["granularity"] = "H"
    pic = expand(pic, "E", value_col="energy_mwh")
    pic = pic[pic["day"] < pd.Timestamp("2023-02-01")]
    a = tr.groupby(["day", "qh", "up"])["energy_mwh"].sum()
    b = pic.groupby(["day", "qh", "up"])["energy_mwh"].sum()
    j = pd.concat([a.rename("t"), b.rename("p")], axis=1).fillna(0.0)
    assert (j["t"] - j["p"]).abs().max() < 1e-6
