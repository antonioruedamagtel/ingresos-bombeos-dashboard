"""Regresion del hallazgo A-1: el precio de RR debe cruzar al cien por cien."""
from ib.engines import balancing_revenue_engine as bal
from ib.util.grid import expand


def test_rr_cobertura_total(i90_month, pmd_month, aliases):
    e = expand(i90_month[i90_month["sheet"] == "I90DIA06"], "E")
    p = expand(i90_month[i90_month["sheet"] == "I90DIA11"], "P")
    out = bal.value_market(e, p, "RR", pmd_month, aliases)
    con = out.loc[out["price"].notna(), "quantity"].abs().sum()
    tot = out["quantity"].abs().sum()
    assert tot > 0
    assert con / tot > 0.999


def test_rr_no_cruza_por_unidad_ni_sentido(i90_month, pmd_month, aliases):
    """La estrategia que casa debe ser la de etiqueta de redespacho."""
    e = expand(i90_month[i90_month["sheet"] == "I90DIA06"], "E")
    p = expand(i90_month[i90_month["sheet"] == "I90DIA11"], "P")
    joined = bal.join_price(e, p, ["tag", "period"],
                            bal.MARKET_JOINS["RR"]["tags"])
    strat = joined.loc[joined["price"].notna(), "price_join"]
    # practicamente todo cruza por etiqueta de redespacho; el resto son periodos
    # en los que solo se publica una serie y cae al respaldo global
    assert (strat == "tag").mean() > 0.999
    assert "up" not in set(strat) and "up_direction" not in set(strat)


def test_aportacion_rr_aguayo(i90_month, pmd_month, aliases):
    e = expand(i90_month[i90_month["sheet"] == "I90DIA06"], "E")
    p = expand(i90_month[i90_month["sheet"] == "I90DIA11"], "P")
    out = bal.value_market(e, p, "RR", pmd_month, aliases)
    ag = out[out["asset"] == "Aguayo"]["revenue_incremental"].sum()
    assert abs(ag - 807_757) < 5_000
