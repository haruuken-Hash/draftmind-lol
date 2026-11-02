"""Pequeños componentes reutilizados por varias vistas."""

from PySide6.QtWidgets import QComboBox, QFrame, QLabel, QVBoxLayout, QWidget

from draftmind.domain.enums import Role

# Texto que Riot pide mostrar en las aplicaciones de terceros (se mantiene en inglés,
# tal como lo publica Riot, con una traducción orientativa debajo).
RIOT_DISCLAIMER = (
    "DraftMind LoL isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games "
    "or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all "
    "associated properties are trademarks or registered trademarks of Riot Games, Inc."
)
RIOT_DISCLAIMER_ES = (
    "DraftMind LoL no está respaldada por Riot Games ni refleja las opiniones de Riot Games ni de nadie "
    "implicado oficialmente en la producción o gestión de sus propiedades. Riot Games y todas sus "
    "propiedades asociadas son marcas comerciales o registradas de Riot Games, Inc."
)

# Traducción de las clases oficiales de Data Dragon.
TAG_LABELS = {
    "Fighter": "Luchador",
    "Tank": "Tanque",
    "Mage": "Mago",
    "Assassin": "Asesino",
    "Marksman": "Tirador",
    "Support": "Apoyo",
}


def title_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("title")
    return label


def subtitle_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("subtitle")
    label.setWordWrap(True)
    return label


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def notice_label(text: str) -> QLabel:
    """Aviso destacado. El texto empieza por "Aviso:" para no depender del color."""
    label = QLabel(f"<b>Aviso:</b> {text}")
    label.setObjectName("notice")
    label.setWordWrap(True)
    return label


def card(parent: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)
    return frame, layout


def page_layout(widget: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(12)
    return layout


def combo_role(box: QComboBox) -> Role | None:
    """Rol elegido en un desplegable.

    Qt guarda los enums que heredan de ``str`` como texto plano ("MIDDLE"),
    así que hay que convertirlos de nuevo a ``Role`` al leerlos.
    """
    data = box.currentData()
    return Role(data) if data else None


def repolish(widget: QWidget) -> None:
    """Vuelve a aplicar el estilo tras cambiar una propiedad dinámica."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
