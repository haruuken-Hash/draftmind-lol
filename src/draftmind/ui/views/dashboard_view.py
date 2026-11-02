"""Pantalla de inicio: estado de los datos, del perfil y guía de lectura."""

from html import escape

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget

from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import ConfidenceLevel, EvidenceKind
from draftmind.ui.widgets import (
    RIOT_DISCLAIMER,
    RIOT_DISCLAIMER_ES,
    card,
    notice_label,
    page_layout,
    section_label,
    subtitle_label,
    title_label,
)


def _card(title: str, body: QLabel) -> QWidget:
    frame, layout = card()
    layout.addWidget(section_label(title))
    body.setWordWrap(True)
    layout.addWidget(body)
    layout.addStretch()
    return frame


class DashboardView(QWidget):
    open_draft = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        layout = page_layout(self)
        layout.addWidget(title_label("Bienvenido a DraftMind"))
        layout.addWidget(subtitle_label(
            "Asistente de estudio para League of Legends. Las recomendaciones son ayudas para "
            "razonar, no certezas: cada una indica sus datos, su tipo de evidencia y su confianza."
        ))
        if ctx.settings.demo_mode:
            layout.addWidget(notice_label(
                "Modo demostración: no hay API key de Riot. El análisis usa perfiles cualitativos de demostración."
            ))

        start = QPushButton("Abrir el tablero de draft")
        start.setObjectName("primary")
        start.clicked.connect(self.open_draft.emit)
        start.setFixedWidth(240)
        layout.addWidget(start)

        self.data_label = QLabel()
        self.profile_label = QLabel()
        evidence = "".join(f"<li><b>{k.label}</b></li>" for k in EvidenceKind)
        levels = " · ".join(lvl.label for lvl in ConfidenceLevel)
        guide = QLabel(
            "Cada afirmación lleva su tipo de evidencia:<ul>" + evidence + "</ul>"
            f"Niveles de confianza: {levels}. Criterios en <i>docs/architecture.md</i>."
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(_card("Datos", self.data_label), 0, 0)
        grid.addWidget(_card("Tu perfil", self.profile_label), 0, 1)
        grid.addWidget(_card("Cómo leer las recomendaciones", guide), 1, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch()
        legal = QLabel(f"{RIOT_DISCLAIMER}<br><i>{RIOT_DISCLAIMER_ES}</i>")
        legal.setWordWrap(True)
        legal.setStyleSheet("color: #8b929c; font-size: 8.5pt;")
        layout.addWidget(legal)
        self.refresh_profile()
        self.set_data_status("")

    def set_data_status(self, status: str) -> None:
        catalog = self._ctx.catalog
        demo = self._ctx.dataset.source
        if catalog.from_data_dragon:
            static = f"Data Dragon <b>{escape(catalog.version or '')}</b> ({escape(catalog.language or '')}), {len(catalog.champions)} campeones"
        else:
            static = "Data Dragon: todavía no descargado"
        self.data_label.setText(
            f"{static}<br>{escape(demo.name)}: {len(self._ctx.dataset.champions)} perfiles"
            + (f"<br><span style='color:#8b929c'>{escape(status)}</span>" if status else "")
        )

    def refresh_profile(self) -> None:
        p = self._ctx.analyzer.profile
        names = {c.id: c.name for c in self._ctx.catalog.champions}
        favorites = ", ".join(names.get(i, i) for i in p.favorite_champions) or "ninguno"
        roles = ", ".join(r.label for r in p.main_roles) or "sin indicar"
        self.profile_label.setText(
            f"Nivel declarado: {p.experience.label}<br>Posiciones: {escape(roles)}<br>"
            f"Preferidos: {escape(favorites)}<br>"
            "<span style='color:#8b929c'>Edítalo en «Fuentes y configuración».</span>"
        )
