"""Genera el extracto compacto utilizado por la demo de GitHub Pages."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ib.domain.aliases import AliasTable
from ib.pipeline import captured_prices, load_assets
from ib.qa import quality_flags as qf
from ib.repositories.processed_store import ProcessedStore
from ib.ui.theme import MARKET_GROUPS


OUTPUT = ROOT / "docs" / "data" / "demo-data.json"
PARTS = ROOT / "data" / "demo_parts"


def records(frame: pd.DataFrame) -> list[dict]:
    clean = frame.replace([np.inf, -np.inf], np.nan)
    return json.loads(clean.to_json(orient="records", date_format="iso", date_unit="s"))


def load_part_frames(filename: str) -> list[pd.DataFrame]:
    return [pd.read_parquet(path) for path in sorted(PARTS.glob(f"????-??/{filename}"))]


def from_history_parts() -> dict | None:
    monthly_frames = load_part_frames("monthly.parquet")
    if not monthly_frames:
        return None
    monthly = pd.concat(monthly_frames, ignore_index=True)
    months = sorted(monthly["month"].unique())
    expected = [period.strftime("%Y-%m") for period in pd.period_range(months[0], months[-1], freq="M")]
    if months != expected:
        missing = sorted(set(expected) - set(months))
        raise RuntimeError(f"Histórico mensual incompleto; faltan: {', '.join(missing)}")

    prices = pd.concat(load_part_frames("prices.parquet"), ignore_index=True)
    prices = prices.drop_duplicates("datetime").sort_values("datetime")

    coverage_raw = pd.concat(load_part_frames("coverage.parquet"), ignore_index=True)
    coverage = coverage_raw.groupby("market", as_index=False).agg(
        cantidad_abs=("cantidad_abs", "sum"), con_precio=("con_precio", "sum"), filas=("filas", "sum")
    )
    observed_market = monthly.groupby("market", as_index=False).agg(rows=("rows", "sum"), observed=("observed_rows", "sum"))
    coverage = coverage.merge(observed_market, on="market", how="left")
    coverage["observado_pct"] = 100 * coverage["observed"] / coverage["rows"].replace(0, np.nan)
    coverage["cobertura_precio_pct"] = 100 * coverage["con_precio"] / coverage["cantidad_abs"].replace(0, np.nan)
    coverage = coverage.drop(columns=["rows", "observed"])

    reconciliation_raw = pd.concat(load_part_frames("reconciliation.parquet"), ignore_index=True)
    numeric = [column for column in reconciliation_raw.select_dtypes(include="number").columns
               if column not in {"residual_pct"}]
    reconciliation = reconciliation_raw.groupby(["entity", "role"], as_index=False)[numeric].sum()
    reconciliation["residual_pct"] = np.where(
        reconciliation["gross_mwh"] > 0,
        100 * reconciliation["residual"].abs() / reconciliation["gross_mwh"], np.nan,
    )
    reconciliation["closes"] = reconciliation["residual_pct"] < 0.5

    meta_parts = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(PARTS.glob("????-??/metadata.json"))]
    start = pd.Period(months[0], freq="M").start_time.date().isoformat()
    end = pd.Period(months[-1], freq="M").end_time.date().isoformat()
    metadata = {
        "period_start": start, "period_end": end,
        "detail_rows": sum(item["detail_rows"] for item in meta_parts),
        "total_revenue_eur": float(monthly["revenue"].sum()),
        "observed_pct": float(100 * monthly["observed_rows"].sum() / monthly["rows"].sum()),
        "quality": {
            "months": len(meta_parts),
            "critical_failed_months": [item["month"] for item in meta_parts if not all(
                item["qa"][key] for key in ("volume", "sign", "trades")
            )],
            "coverage_failed_months": [item["month"] for item in meta_parts if not item["qa"]["coverage"]],
        },
    }
    return {"monthly": monthly, "prices": prices, "coverage": coverage,
            "reconciliation": reconciliation, "metadata": metadata}


def from_processed_store(aliases: AliasTable) -> dict:
    store = ProcessedStore(ROOT / "data")
    detail = store.read("revenue_detail").copy()
    pmd = store.read("pmd").copy()
    reconciliation = store.read("volume_reconciliation").copy()
    detail["datetime"] = pd.to_datetime(detail["datetime"])
    detail["month"] = detail["datetime"].dt.strftime("%Y-%m")
    detail["role"] = detail["up"].map(aliases.role_of).fillna("unknown")
    detail["market_group"] = detail["market"].map(MARKET_GROUPS).fillna("Otros")
    detail["observed_rows"] = (detail["data_class"] == "OBSERVADO").astype(int)
    detail["estimated_revenue"] = np.where(
        detail["data_class"] == "ESTIMADO", detail["revenue_incremental"], 0.0
    )
    monthly = detail.groupby(
        ["month", "asset", "market", "market_group", "role"], as_index=False
    ).agg(
        revenue=("revenue_incremental", "sum"), quantity=("quantity", "sum"), rows=("quantity", "size"),
        observed_rows=("observed_rows", "sum"), estimated_revenue=("estimated_revenue", "sum"),
    )
    pmd["day"] = pd.to_datetime(pmd["day"])
    pmd["datetime"] = pmd["day"] + pd.to_timedelta((pmd["qh"] - 1) * 15, unit="m")
    prices = pmd.set_index("datetime")["pmd"].resample("1h").mean().rename("price").reset_index()
    return {
        "monthly": monthly, "prices": prices, "coverage": qf.coverage(detail),
        "reconciliation": reconciliation,
        "metadata": {
            "period_start": detail["datetime"].min().date().isoformat(),
            "period_end": detail["datetime"].max().date().isoformat(),
            "detail_rows": int(len(detail)), "total_revenue_eur": float(detail["revenue_incremental"].sum()),
            "observed_pct": float(100 * (detail["data_class"] == "OBSERVADO").mean()),
            "quality": {"months": 1, "critical_failed_months": [], "coverage_failed_months": []},
        },
        "captured": captured_prices(detail, aliases),
    }


def main() -> None:
    assets = load_assets(ROOT / "config" / "assets.csv")
    aliases = AliasTable.from_assets(assets)
    source = from_history_parts() or from_processed_store(aliases)
    monthly, prices = source["monthly"].copy(), source["prices"].copy()
    coverage, reconciliation = source["coverage"].copy(), source["reconciliation"].copy()
    for column in ("revenue", "quantity", "estimated_revenue"):
        monthly[column] = monthly[column].round(5)
    prices["price"] = prices["price"].round(5)
    for column in coverage.select_dtypes(include="number").columns:
        coverage[column] = coverage[column].round(3)

    captured_rows = []
    for role in ("generation", "pumping"):
        revenue = monthly[(monthly["role"] == role) & (monthly["market"] != "AFRR_BANDA")].groupby("asset")["revenue"].sum()
        p48 = monthly[(monthly["role"] == role) & (monthly["market"] == "DA")].groupby("asset")["quantity"].sum()
        for asset in sorted(set(revenue.index) | set(p48.index)):
            volume, cash = float(p48.get(asset, 0)), float(revenue.get(asset, 0))
            captured_rows.append({"asset": asset, "role": role, "p48_mwh": volume,
                                  "revenue": cash, "precio_capturado": cash / volume if volume else np.nan})
    captured = pd.DataFrame(captured_rows)
    for column, digits in (("p48_mwh", 3), ("revenue", 2), ("precio_capturado", 4)):
        captured[column] = captured[column].round(digits)

    asset_revenue = monthly.groupby("asset")["revenue"].sum()
    asset_rows = monthly.groupby("asset")["rows"].sum()
    asset_observed = monthly.groupby("asset")["observed_rows"].sum()
    catalog_columns = ["asset_id", "asset", "operator", "comunidad_autonoma", "provincia",
                       "mw_reference", "include_default", "mercados_habilitados"]
    catalog = assets[catalog_columns].copy()
    catalog["revenue"] = catalog["asset"].map(asset_revenue).fillna(0).round(2)
    catalog["observed_pct"] = (100 * catalog["asset"].map(asset_observed) / catalog["asset"].map(asset_rows)).round(2)

    selected = monthly[monthly["market"] == "DA"]
    generation = selected.loc[selected["role"] == "generation", "quantity"].sum()
    pumping = selected.loc[selected["role"] == "pumping", "quantity"].sum()
    meta = source["metadata"]
    payload = {
        "metadata": {
            "title": "INGRESOS BOMBEOS · Demo pública",
            "period_start": meta["period_start"], "period_end": meta["period_end"],
            "detail_rows": int(meta["detail_rows"]), "assets": int(monthly["asset"].nunique()),
            "total_revenue_eur": round(float(meta["total_revenue_eur"]), 2),
            "generation_mwh_p48": round(float(generation), 3),
            "pumping_mwh_p48": round(float(abs(pumping)), 3),
            "observed_pct": round(float(meta["observed_pct"]), 2),
            "sources": ["OMIE", "REE / e·sios"], "snapshot": True,
            "quality": meta["quality"],
            "generated_from": "agregaciones mensuales validadas de la versión 1.0",
        },
        "market_groups": list(dict.fromkeys(MARKET_GROUPS.values())),
        "assets": records(catalog), "monthly": records(monthly), "prices": records(prices),
        "captured_prices": records(captured), "coverage": records(coverage),
        "reconciliation": records(reconciliation),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUTPUT.write_text(encoded, encoding="utf-8")
    # El mismo snapshot como script permite abrir index.html con doble clic.
    # GitHub Pages utiliza el JSON y ambos formatos contienen solo agregados.
    OUTPUT.with_suffix(".js").write_text(f"window.DEMO_DATA={encoded};\n", encoding="utf-8")
    print(f"{OUTPUT} · {OUTPUT.stat().st_size:,} bytes · {meta['period_start']} a {meta['period_end']}")


if __name__ == "__main__":
    main()
