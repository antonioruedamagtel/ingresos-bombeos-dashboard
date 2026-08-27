"""Alias de unidades de programación por fuente y periodo.

Regla del proyecto, confirmada en la auditoría: una central no tiene un código
único ni eterno, y el código puede diferir entre OMIE e I90 y entre periodos.
No existe un diccionario global rígido: cada alias lleva fuente y vigencia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class UnitAlias:
    code: str
    asset: str
    role: str                 # 'generation' | 'pumping'
    source: str = "ANY"       # 'I90' | 'OMIE' | 'ANY'
    valid_from: str | None = None
    valid_to: str | None = None

    def active(self, when: pd.Timestamp | None = None, source: str = "ANY") -> bool:
        if self.source != "ANY" and source != "ANY" and self.source != source:
            return False
        if when is None:
            return True
        if self.valid_from and pd.Timestamp(when) < pd.Timestamp(self.valid_from):
            return False
        if self.valid_to and pd.Timestamp(when) > pd.Timestamp(self.valid_to):
            return False
        return True


@dataclass
class AliasTable:
    aliases: list[UnitAlias] = field(default_factory=list)

    @classmethod
    def from_assets(cls, assets: pd.DataFrame) -> "AliasTable":
        out: list[UnitAlias] = []
        for r in assets.itertuples():
            for col, role in (("up_generation", "generation"), ("up_pumping", "pumping")):
                raw = getattr(r, col, "") or ""
                for code in [c.strip().upper() for c in str(raw).split("|") if c.strip()]:
                    out.append(UnitAlias(code=code, asset=r.asset, role=role))
        return cls(out)

    def codes(self, when=None, source="ANY") -> set[str]:
        return {a.code for a in self.aliases if a.active(when, source)}

    def asset_of(self, code: str, when=None, source="ANY") -> str | None:
        c = str(code).strip().upper()
        for a in self.aliases:
            if a.code == c and a.active(when, source):
                return a.asset
        return None

    def role_of(self, code: str, when=None, source="ANY") -> str | None:
        c = str(code).strip().upper()
        for a in self.aliases:
            if a.code == c and a.active(when, source):
                return a.role
        return None

    def as_frame(self) -> pd.DataFrame:
        return pd.DataFrame([a.__dict__ for a in self.aliases])
