"""Nunca se reaplica un signo de rol sobre una fuente con signo nativo."""
from ib.engines import physical_program_engine as phys


def test_p48_trae_signo_nativo(i90_month):
    p48 = i90_month[i90_month["sheet"] == "I90DIA02"]
    agug = p48[p48["up"] == "AGUG"]["value"]
    agub = p48[p48["up"] == "AGUB"]["value"]
    assert (agug > 0).all()
    assert (agub < 0).all()


def test_no_hay_conflicto_de_signo(i90_month, aliases):
    chk = phys.check_native_sign(i90_month, aliases)
    assert not chk["conflict"].any()


def test_volumenes_p48_de_aguayo(i90_month):
    p48 = phys.p48(i90_month)
    g = p48[p48["up"] == "AGUG"]["energy_mwh"].sum()
    b = p48[p48["up"] == "AGUB"]["energy_mwh"].sum()
    assert abs(g - 59493.8) < 1.0
    assert abs(b + 88939.2) < 1.0
