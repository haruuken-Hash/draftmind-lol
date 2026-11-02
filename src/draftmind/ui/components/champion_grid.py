"""Cuadrícula de retratos con buscador y filtro por clase.

Usa un QListWidget en modo icono: ya trae navegación con teclado (flechas,
Intro) y es eficiente con cientos de elementos.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from draftmind.domain.enums import ProfileOrigin
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.widgets import TAG_LABELS

ICON_SIZE = 52


class ChampionGrid(QWidget):
    champion_chosen = Signal(str)     # Clic o Intro sobre un campeón.
    champion_selected = Signal(str)   # Cambio de selección (para vistas de detalle).

    def __init__(self, ctx, portraits: PortraitProvider, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._portraits = portraits
        self._unavailable: set[str] = set()

        self.search = QLineEdit(placeholderText="Buscar campeón…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.tag_filter = QComboBox()
        self.tag_filter.addItem("Todas las clases", None)
        for tag, label in TAG_LABELS.items():
            self.tag_filter.addItem(label, tag)
        self.only_profiled = QCheckBox("Solo perfiles revisados")
        self.only_profiled.setToolTip(
            "Oculta los campeones cuyo perfil es solo una estimación automática."
        )

        self.list = QListWidget()
        self.list.setObjectName("grid")
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.list.setGridSize(QSize(ICON_SIZE + 26, ICON_SIZE + 34))
        self.list.setUniformItemSizes(True)
        self.list.setWordWrap(True)
        self.list.setSpacing(2)

        filters = QHBoxLayout()
        filters.addWidget(self.search, 3)
        filters.addWidget(self.tag_filter, 2)
        filters.addWidget(self.only_profiled)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(filters)
        layout.addWidget(self.list, 1)

        self.search.textChanged.connect(self._apply_filters)
        self.tag_filter.currentIndexChanged.connect(self._apply_filters)
        self.only_profiled.toggled.connect(self._apply_filters)
        self.list.itemClicked.connect(self._emit_chosen)
        self.list.itemActivated.connect(self._emit_chosen)  # Intro / doble clic.
        self.list.currentItemChanged.connect(
            lambda item, _: item and self.champion_selected.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        self.reload()

    def reload(self) -> None:
        """Reconstruye los elementos (p. ej. tras descargar Data Dragon)."""
        self.list.clear()
        for champion in self._ctx.catalog.champions:
            item = QListWidgetItem(QIcon(self._portraits.get(champion.id, ICON_SIZE)), champion.name)
            item.setData(Qt.ItemDataRole.UserRole, champion.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, champion.tags)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            tooltip = f"{champion.name}" + (f" — {champion.title}" if champion.title else "")
            if self._ctx.analyzer.has_profile(champion.id):
                tooltip += f"\nPerfil: {self._ctx.analyzer.champion(champion.id).origin.label}"
            else:
                tooltip += "\nSin perfil cualitativo: no participa en las recomendaciones."
            item.setToolTip(tooltip)
            self.list.addItem(item)
        self.set_unavailable(self._unavailable)
        self._apply_filters()

    def set_unavailable(self, champion_ids: set[str]) -> None:
        """Atenúa y desactiva los campeones que ya están en el draft."""
        self._unavailable = set(champion_ids)
        for i in range(self.list.count()):
            item = self.list.item(i)
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            if item.data(Qt.ItemDataRole.UserRole) in self._unavailable:
                flags = Qt.ItemFlag.NoItemFlags
            item.setFlags(flags)

    def _apply_filters(self) -> None:
        text = self.search.text().strip().lower()
        tag = self.tag_filter.currentData()
        only_profiled = self.only_profiled.isChecked()
        for i in range(self.list.count()):
            item = self.list.item(i)
            champion_id = item.data(Qt.ItemDataRole.UserRole)
            visible = (
                text in item.text().lower()
                and (tag is None or tag in item.data(Qt.ItemDataRole.UserRole + 1))
                and (not only_profiled or self._is_reviewed(champion_id))
            )
            item.setHidden(not visible)

    def _is_reviewed(self, champion_id: str) -> bool:
        analyzer = self._ctx.analyzer
        return analyzer.has_profile(champion_id) and \
            analyzer.champion(champion_id).origin is not ProfileOrigin.ESTIMATED

    def _emit_chosen(self, item: QListWidgetItem) -> None:
        if item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self.champion_chosen.emit(item.data(Qt.ItemDataRole.UserRole))
