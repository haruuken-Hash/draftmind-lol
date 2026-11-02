"""Punto de entrada: python main.py"""

import sys
from pathlib import Path

# Permite ejecutar sin instalar el paquete: añade src/ a la ruta de importación.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from draftmind.app.bootstrap import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
