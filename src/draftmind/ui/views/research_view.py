"""Registro de fuentes de investigación (notas de parche, análisis, documentación).

No descarga ni resume páginas automáticamente: el usuario registra la
fuente, qué afirma y si la ha contrastado. Así se distinguen las fuentes
primarias de las opiniones y nada se trata como verificado por defecto.
"""

from datetime import datetime, timezone
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import SourceType, Verification
from draftmind.domain.models import ResearchSource
from draftmind.ui.widgets import card, page_layout, subtitle_label, title_label

OFFICIAL_STARTING_POINTS = [
    ("Documentación de LoL para desarrolladores (Riot)", "https://developer.riotgames.com/docs/lol"),
    ("Política de aplicaciones de terceros (Riot)", "https://support.riotgames.com/es-es/riot/events/third-party-applications"),
    ("Data Dragon: versiones publicadas", "https://ddragon.leagueoflegends.com/api/versions.json"),
]


class ResearchView(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.editing_id: int | None = None
        layout = page_layout(self)
        layout.addWidget(title_label("Investigación"))
        layout.addWidget(subtitle_label(
            "Registra las fuentes que consultes: notas de parche, cambios de balance, explicaciones de "
            "mecánicas o análisis. Prioriza las oficiales para cambios de mecánicas. Una fuente no se da por "
            "buena hasta contrastarla con otra."
        ))
        starts = " · ".join(f"<a href='{u}' style='color:#17c3a5'>{escape(t)}</a>" for t, u in OFFICIAL_STARTING_POINTS)
        links = QLabel(f"Puntos de partida oficiales: {starts}")
        links.setOpenExternalLinks(True)
        links.setWordWrap(True)
        layout.addWidget(links)

        form_box, form_layout = card()
        form = QFormLayout()
        self.url = QLineEdit(placeholderText="https://…")
        self.title = QLineEdit()
        self.source_type = QComboBox()
        for t in SourceType:
            self.source_type.addItem(t.label, t.value)
        self.published = QLineEdit(placeholderText="Si se conoce, p. ej. 22/10/2026")
        self.patch = QLineEdit(placeholderText="p. ej. 16.21")
        self.claim = QPlainTextEdit()
        self.claim.setPlaceholderText("Qué afirma la fuente, con tus palabras")
        self.claim.setMaximumHeight(60)
        self.verification = QComboBox()
        for v in Verification:
            self.verification.addItem(v.label, v.value)
        self.notes = QLineEdit(placeholderText="Con qué la contrastaste, dudas…")
        for label, widget in (("URL:", self.url), ("Título:", self.title), ("Tipo:", self.source_type),
                              ("Publicada:", self.published), ("Parche:", self.patch), ("Afirmación:", self.claim),
                              ("Verificación:", self.verification), ("Notas:", self.notes)):
            form.addRow(label, widget)
        form_layout.addLayout(form)
        buttons = QHBoxLayout()
        self.save_button = QPushButton("Guardar fuente")
        self.save_button.setObjectName("primary")
        new_button = QPushButton("Nueva")
        delete_button = QPushButton("Eliminar seleccionada")
        self.status = QLabel()
        for b in (self.save_button, new_button, delete_button):
            buttons.addWidget(b)
        buttons.addWidget(self.status, 1)
        form_layout.addLayout(buttons)
        layout.addWidget(form_box)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Título", "Tipo", "Parche", "Verificación", "Consultada", "URL"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.save_button.clicked.connect(self.save)
        new_button.clicked.connect(self.clear_form)
        delete_button.clicked.connect(self.delete_selected)
        self.table.cellClicked.connect(self._load_row)
        self._sources: list[ResearchSource] = []
        self.reload()

    def reload(self) -> None:
        self._sources = self.ctx.research.list()
        self.table.setRowCount(len(self._sources))
        for row, s in enumerate(self._sources):
            values = [s.title, s.source_type.label, s.patch or "—", s.verification.label,
                      s.retrieved_at.astimezone().strftime("%d/%m/%Y"), s.url]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def save(self) -> None:
        url, title = self.url.text().strip(), self.title.text().strip()
        if not url.startswith(("http://", "https://")) or not title:
            self.status.setText("Indica un título y una URL que empiece por http:// o https://.")
            return
        existing = next((s for s in self._sources if s.id == self.editing_id), None)
        source = ResearchSource(
            id=self.editing_id, url=url, title=title,
            source_type=SourceType(self.source_type.currentData()),
            published_on=self.published.text().strip(),
            retrieved_at=existing.retrieved_at if existing else datetime.now(timezone.utc),
            patch=self.patch.text().strip(), claim=self.claim.toPlainText().strip(),
            verification=Verification(self.verification.currentData()), notes=self.notes.text().strip(),
        )
        saved = self.ctx.research.save(source)
        self.editing_id = saved.id
        self.status.setText("Fuente guardada.")
        self.reload()

    def clear_form(self) -> None:
        self.editing_id = None
        for w in (self.url, self.title, self.published, self.patch, self.notes):
            w.clear()
        self.claim.clear()
        self.source_type.setCurrentIndex(0)
        self.verification.setCurrentIndex(0)
        self.status.clear()

    def _load_row(self, row: int, _col: int) -> None:
        s = self._sources[row]
        self.editing_id = s.id
        self.url.setText(s.url)
        self.title.setText(s.title)
        self.source_type.setCurrentIndex(self.source_type.findData(s.source_type.value))
        self.published.setText(s.published_on)
        self.patch.setText(s.patch)
        self.claim.setPlainText(s.claim)
        self.verification.setCurrentIndex(self.verification.findData(s.verification.value))
        self.notes.setText(s.notes)
        self.status.setText("Editando la fuente seleccionada.")

    def delete_selected(self) -> None:
        if self.editing_id is None:
            self.status.setText("Selecciona primero una fuente de la tabla.")
            return
        if QMessageBox.question(self, "Eliminar fuente", "¿Eliminar la fuente seleccionada?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.ctx.research.delete(self.editing_id)
        self.clear_form()
        self.reload()
