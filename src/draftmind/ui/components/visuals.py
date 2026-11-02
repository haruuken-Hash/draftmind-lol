"""Componentes visuales: iconos, banners con ilustración, cifras, rango y forma.

Los iconos salen de la fuente de iconos de Windows (Segoe Fluent Icons, o
Segoe MDL2 Assets en Windows 10): no hacen falta imágenes externas.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from draftmind.ui import theme

# Códigos de los iconos (comprobados renderizando la fuente).
ICONS = {
    "home": 0xE80F, "profile": 0xE77B, "champions": 0xE716, "draft": 0xE7FC, "counters": 0xEA18,
    "builds": 0xE945, "strategy": 0xE7C1, "history": 0xE81C, "analysis": 0xE9D2, "research": 0xE7BE,
    "settings": 0xE713, "search": 0xE721, "refresh": 0xE72C, "star": 0xE734,
}


def icon_font() -> str:
    families = QFontDatabase.families()
    return theme.ICON_FONT if theme.ICON_FONT in families else theme.FALLBACK_ICON_FONT


def glyph_pixmap(name: str, size: int = 18, color: str = theme.TEXT) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont(icon_font())
    font.setPixelSize(int(size * 0.85))
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, chr(ICONS[name]))
    painter.end()
    return pixmap


def glyph_icon(name: str, size: int = 18) -> QIcon:
    """Icono con color normal y color de acento al estar seleccionado."""
    icon = QIcon()
    icon.addPixmap(glyph_pixmap(name, size, theme.MUTED), QIcon.Mode.Normal)
    icon.addPixmap(glyph_pixmap(name, size, theme.ACCENT), QIcon.Mode.Selected)
    return icon


def add_shadow(widget: QWidget, blur: int = 24, alpha: int = 110) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 6)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


class HeroBanner(QFrame):
    """Banner con la ilustración de un campeón de fondo y un degradado para el texto."""

    def __init__(self, height: int = 190, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._image: QPixmap | None = None
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(28, 22, 28, 22)
        self.content.setSpacing(6)

    def set_image(self, pixmap: QPixmap | None) -> None:
        self._image = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (nombre de Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        painter.setClipPath(path)
        if self._image is not None:
            # Recorte tipo «cover»: llena el banner manteniendo la proporción, centrado arriba.
            scaled = self._image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                        Qt.TransformationMode.SmoothTransformation)
            x = (scaled.width() - self.width()) // 2
            y = max(0, (scaled.height() - self.height()) // 4)
            painter.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
        else:
            painter.fillRect(rect, QColor(theme.SURFACE_2))
        shade = QLinearGradient(0, 0, rect.width(), 0)
        shade.setColorAt(0.0, QColor(11, 14, 19, 245))
        shade.setColorAt(0.55, QColor(11, 14, 19, 170))
        shade.setColorAt(1.0, QColor(11, 14, 19, 40))
        painter.fillRect(rect, shade)
        bottom = QLinearGradient(0, rect.height() * 0.5, 0, rect.height())
        bottom.setColorAt(0, QColor(11, 14, 19, 0))
        bottom.setColorAt(1, QColor(11, 14, 19, 200))
        painter.fillRect(rect, bottom)
        painter.setPen(QColor(theme.BORDER))
        painter.drawPath(path)
        painter.end()


def stat_tile(value: str, caption: str, accent: str | None = None) -> tuple[QFrame, QLabel]:
    """Tarjeta con una cifra grande. Devuelve (tarjeta, etiqueta del valor)."""
    frame = QFrame()
    frame.setObjectName("tile")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(2)
    value_label = QLabel(value)
    value_label.setObjectName("statValue")
    if accent:
        value_label.setStyleSheet(f"color: {accent};")
    caption_label = QLabel(caption.upper())
    caption_label.setObjectName("statCaption")
    layout.addWidget(value_label)
    layout.addWidget(caption_label)
    return frame, value_label


def rank_pill(tier: str, text: str) -> QLabel:
    color = theme.TIER_COLORS.get(tier, theme.MUTED)
    label = QLabel(text)
    label.setStyleSheet(
        f"background: {color}22; color: {color}; border: 1px solid {color}; border-radius: 10px;"
        "padding: 3px 12px; font-weight: 800; font-size: 10pt;"
    )
    return label


def result_chip(win: bool) -> QLabel:
    """«V» o «D» con color (texto incluido para no depender del color)."""
    color, bg = (theme.WIN, theme.WIN_BG) if win else (theme.LOSS, theme.LOSS_BG)
    label = QLabel("V" if win else "D")
    label.setFixedSize(22, 22)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setToolTip("Victoria" if win else "Derrota")
    label.setStyleSheet(f"background: {bg}; color: {color}; border-radius: 6px; font-weight: 800; font-size: 8.5pt;")
    return label


def form_row(results: list[bool]) -> QWidget:
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(3)
    for win in results:
        row.addWidget(result_chip(win))
    row.addStretch()
    return widget


def badge_label(badge: str | None) -> str:
    """HTML de la insignia MVP/ACE."""
    if badge == "MVP":
        return f"<span style='color:{theme.GOLD}; font-weight:800'>MVP</span>"
    if badge == "ACE":
        return f"<span style='color:{theme.ACE}; font-weight:800'>ACE</span>"
    return ""
