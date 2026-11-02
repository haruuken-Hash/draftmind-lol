"""Retratos de campeones con esquinas redondeadas.

Si la imagen no está descargada se dibuja un cuadro con las iniciales, de
modo que la interfaz funciona igual sin conexión.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap

from draftmind.ui import theme

_EMPTY_ID = "__empty__"


class PortraitProvider:
    def __init__(self, ctx):
        self._ctx = ctx
        self._cache: dict[tuple[str, int], QPixmap] = {}

    def invalidate(self) -> None:
        self._cache.clear()

    def get(self, champion_id: str | None, size: int) -> QPixmap:
        key = (champion_id or _EMPTY_ID, size)
        if key not in self._cache:
            self._cache[key] = self._build(champion_id, size)
        return self._cache[key]

    def asset(self, relative: str | None, size: int, fallback: str) -> QPixmap:
        """Icono de objeto, hechizo o runa guardado en la caché de Data Dragon."""
        key = (f"asset:{relative}:{fallback}", size)
        if key not in self._cache:
            path = self._ctx.catalogs.client.cached_image(relative) if relative else None
            self._cache[key] = self._render(QPixmap(str(path)) if path else None, fallback, size)
        return self._cache[key]

    def item(self, item_id: int, size: int) -> QPixmap:
        data = self._ctx.game_data
        relative = f"{data.version}/img/item/{item_id}.png" if data else None
        return self.asset(relative, size, str(item_id)[-2:])

    def _build(self, champion_id: str | None, size: int) -> QPixmap:
        source = None
        if champion_id:
            catalog = self._ctx.catalog
            info = next((c for c in catalog.champions if c.id == champion_id), None)
            path = self._ctx.catalogs.image_path(catalog, info) if info else None
            if path:
                source = QPixmap(str(path))
        text = _initials(champion_id) if champion_id else "+"
        return self._render(source, text, size)

    def _render(self, source: QPixmap | None, text: str, size: int) -> QPixmap:
        if source is not None and source.isNull():
            source = None
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, size, size), size * 0.18, size * 0.18)
        painter.setClipPath(clip)
        if source is not None:
            painter.drawPixmap(0, 0, size, size, source)
        else:
            painter.fillRect(0, 0, size, size, QColor(theme.SURFACE_2))
            painter.setPen(QColor(theme.MUTED))
            font = QFont("Segoe UI", max(6, size // 4))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        return result


def _initials(champion_id: str) -> str:
    capitals = [ch for ch in champion_id if ch.isupper()]
    return ("".join(capitals[:2]) or champion_id[:2]).upper()
