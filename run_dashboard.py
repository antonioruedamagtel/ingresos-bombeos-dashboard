"""Lanzador del cuadro de mando."""
from pathlib import Path

from ib.ui.dashboard import build_app

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    import os
    data_root = Path(os.getenv("IB_DATA_ROOT", ROOT / "data"))
    app = build_app(data_root, ROOT / "config" / "assets.csv")
    app.run(host="127.0.0.1", port=8050, debug=False)
