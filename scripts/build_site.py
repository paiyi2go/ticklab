"""Build the static demo: the page plus the Python sources it runs in the browser via Pyodide."""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "ticklab"
MODULES = ("__init__", "analyze", "synth", "diagnose", "demo")


def build(out: Path) -> None:
    shutil.rmtree(out, ignore_errors=True)
    (out / "py" / "ticklab").mkdir(parents=True)
    shutil.copy(PACKAGE / "static" / "index.html", out / "index.html")
    for name in MODULES:
        shutil.copy(PACKAGE / f"{name}.py", out / "py" / "ticklab" / f"{name}.py")
    (out / ".nojekyll").touch()  # GitHub Pages would otherwise skip __init__.py


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site")
