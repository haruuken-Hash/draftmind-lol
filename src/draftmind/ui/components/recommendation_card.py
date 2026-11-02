"""Tarjeta con el análisis de un candidato."""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from draftmind.domain.enums import EvidenceKind, ProfileOrigin
from draftmind.domain.models import CandidateAnalysis
from draftmind.ui.draft_report import rating_text
from draftmind.ui.portraits import PortraitProvider

MAX_POINTS = 3


class RecommendationCard(QFrame):
    pick_requested = Signal(str)

    def __init__(
        self,
        analysis: CandidateAnalysis,
        portraits: PortraitProvider,
        caption: str | None = None,
        can_pick: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("card")
        self.analysis = analysis
        champion = analysis.champion

        portrait = QLabel()
        portrait.setPixmap(portraits.get(champion.id, 44))
        name = QLabel(f"<b>{escape(champion.name)}</b>")
        name.setStyleSheet("font-size: 11.5pt;")
        confidence = QLabel(f"Confianza: {analysis.confidence.level.label}")
        confidence.setObjectName("confidence")
        confidence.setToolTip("\n".join(analysis.confidence.reasons + analysis.confidence.warnings))

        score = QProgressBar()
        score.setRange(0, 100)
        score.setValue(round(analysis.score))
        score.setFormat(f"{analysis.score:.0f}/100")
        score.setToolTip("Puntuación orientativa de criterios cualitativos. No es un win rate.")

        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        if caption:
            cap = QLabel(caption.upper())
            cap.setStyleSheet("color: #17c3a5; font-size: 8pt; font-weight: 700;")
            header_text.addWidget(cap)
        header_text.addWidget(name)
        if champion.origin is ProfileOrigin.ESTIMATED:
            origin = QLabel("Perfil estimado automáticamente")
            origin.setStyleSheet("color: #f0b429; font-size: 8.5pt;")
            origin.setToolTip("Calculado a partir de la clase y las valoraciones oficiales. "
                              "Puedes revisarlo en «Campeones».")
            header_text.addWidget(origin)
        header_text.addWidget(score)
        header = QHBoxLayout()
        header.addWidget(portrait, 0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(header_text, 1)

        points = QLabel(self._points_html())
        points.setWordWrap(True)
        points.setTextFormat(Qt.TextFormat.RichText)

        self.details = QLabel(self._details_html())
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.hide()
        toggle = QPushButton("Ver criterios")
        toggle.setObjectName("link")
        toggle.clicked.connect(lambda: self._toggle(toggle))

        footer = QHBoxLayout()
        footer.addWidget(confidence)
        footer.addWidget(toggle)
        footer.addStretch()
        if can_pick:
            pick = QPushButton("Elegir")
            pick.setObjectName("primary")
            pick.setToolTip("Coloca este campeón en tu casilla del tablero (no actúa sobre el cliente del juego).")
            pick.clicked.connect(lambda: self.pick_requested.emit(champion.id))
            footer.addWidget(pick)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(points)
        layout.addWidget(self.details)
        layout.addStretch()
        layout.addLayout(footer)

    def _points_html(self) -> str:
        a = self.analysis
        pros = "".join(f"<div>+ {escape(p)}</div>" for p in a.pros[:MAX_POINTS])
        cons = "".join(f"<div>− {escape(c)}</div>" for c in a.cons[:MAX_POINTS])
        if not pros and not cons:
            return "<i style='color:#8b929c'>Sin ventajas ni desventajas destacables con los datos disponibles.</i>"
        return (
            (f"<div style='color:#7ee2c9'><b>Ventajas</b></div>{pros}" if pros else "")
            + (f"<div style='color:#ff9aa4; margin-top:4px'><b>Desventajas</b></div>{cons}" if cons else "")
        )

    def _details_html(self) -> str:
        rows = []
        for f in self.analysis.factors:
            muted = f.kind is EvidenceKind.INSUFFICIENT
            style = " style='color:#8b929c'" if muted else ""
            rows.append(
                f"<div{style}><b>{escape(f.label)}</b> — {rating_text(f)} "
                f"<i>({escape(f.kind.label)})</i><br>{escape(f.explanation)}</div>"
            )
        warnings = "".join(
            f"<div style='color:#f0b429'><b>Advertencia:</b> {escape(w)}</div>"
            for w in self.analysis.confidence.warnings
        )
        return "<div style='margin-top:4px'>" + "<br>".join(rows) + warnings + "</div>"

    def _toggle(self, button: QPushButton) -> None:
        visible = not self.details.isVisible()
        self.details.setVisible(visible)
        button.setText("Ocultar criterios" if visible else "Ver criterios")
