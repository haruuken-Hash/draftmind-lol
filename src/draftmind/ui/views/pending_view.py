"""Pantalla para secciones que todavía no están implementadas.

Deja claro qué etapa las implementará, para no aparentar funciones que no existen.
"""

from PySide6.QtWidgets import QLabel, QWidget

from draftmind.ui.widgets import card, notice_label, page_layout, subtitle_label, title_label


class PendingView(QWidget):
    def __init__(self, title: str, stage: int, planned: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        layout = page_layout(self)
        layout.addWidget(title_label(title))
        layout.addWidget(notice_label(
            f"Esta sección todavía no está implementada. Está prevista para la etapa {stage}."
        ))
        layout.addWidget(subtitle_label("Qué incluirá:"))
        box, box_layout = card()
        items = QLabel("<ul>" + "".join(f"<li>{p}</li>" for p in planned) + "</ul>")
        items.setWordWrap(True)
        box_layout.addWidget(items)
        layout.addWidget(box)
        layout.addStretch()
