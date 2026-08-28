import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_static_demo_has_required_assets():
    for relative in (
        "index.html", "styles.css", "app.js", ".nojekyll",
        "vendor/plotly.min.js", "data/demo-data.json",
    ):
        path = DOCS / relative
        assert path.exists(), relative
        if relative != ".nojekyll":
            assert path.stat().st_size > 0, relative


def test_snapshot_contains_eight_plants_through_april_2026():
    payload = json.loads((DOCS / "data" / "demo-data.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["period_start"] == "2023-01-01"
    assert payload["metadata"]["period_end"] == "2026-04-30"
    assert {row["asset"] for row in payload["assets"]} == {
        "Aguayo", "Guillena", "Ip", "Moralets", "La Muela", "Sallente",
        "Tajo de la Encantada", "Bolarque II",
    }
    assert {row["month"] for row in payload["monthly"]} == {
        f"{year:04d}-{month:02d}"
        for year in range(2023, 2027)
        for month in range(1, 13)
        if (year, month) <= (2026, 4)
    }


def test_public_demo_contains_no_esios_credential():
    public_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in DOCS.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".json", ".md"}
    )
    assert re.search(r"ESIOS_API_KEY=[0-9a-fA-F]{64}", public_text) is None
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in DOCS.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".json"}
    )
    assert "x-api-key" not in runtime_text.lower()
    env_path = ROOT / ".env"
    if env_path.exists():
        token = env_path.read_text(encoding="utf-8").partition("=")[2].strip()
        assert token and token not in public_text


def test_storage_modes_are_mutually_exclusive_in_the_demo():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    javascript = (DOCS / "app.js").read_text(encoding="utf-8")
    assert 'id="storage-mode"' in html
    assert 'id="useful-mwh"' in html
    assert 'id="volume-hm3"' in html and 'id="head-m"' in html
    assert '$("#useful-mwh").disabled = reservoir' in javascript
    assert '$("#volume-hm3").disabled = !reservoir' in javascript
    assert '$("#head-m").disabled = !reservoir' in javascript


def test_public_links_and_requested_metric_are_present():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    assert "antonio-rueda-caballero-21665323b" in html
    assert "antonioruedamagtel/ingresos-bombeos-dashboard" in html
    assert "EUR/MW-año" in html
