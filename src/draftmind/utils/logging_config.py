"""Registro de eventos en consola y en un archivo dentro de la carpeta de datos."""

import logging
from pathlib import Path


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "draftmind.log", encoding="utf-8"),
        ],
        force=True,
    )
    # httpx registra cada petición en INFO; solo interesan sus avisos y errores.
    logging.getLogger("httpx").setLevel(logging.WARNING)
