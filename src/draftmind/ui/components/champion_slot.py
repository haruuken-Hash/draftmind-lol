"""Casilla del tablero de draft: un campeón en una posición de un equipo.

Ratón: clic = activar la casilla; clic derecho = vaciarla.
Teclado: Tab para llegar, Intro/Espacio = activar, Supr/Retroceso = vaciar.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from draftmind.domain.enums import Role
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.widgets import combo_role, repolish

PORTRAIT = 48


class ChampionSlot(QFrame):
    activated = Signal(object)  # Emite la propia casilla.
    cleared = Signal(object)
    role_changed = Signal(object)

    def __init__(
        self,
        portraits: PortraitProvider,
        role: Role,
        editable_role: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("slot")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._portraits = portraits
        self.champion_id: str | None = None
        self.champion_name: str | None = None
        self.cell_id: int | None = None  # Casilla del cliente en el draft en vivo.
        self.tentative = False
        self._role = role
        self._is_me = False

        self.portrait = QLabel()
        self.portrait.setFixedSize(PORTRAIT, PORTRAIT)
        self.name = QLabel()
        self.name.setStyleSheet("font-weight: 600;")
        self.detail = QLabel()
        self.detail.setProperty("class", "muted")
        self.detail.setStyleSheet("color: #8b929c; font-size: 9pt;")
        self.me_badge = QLabel("TÚ")
        self.me_badge.setObjectName("badge")
        self.me_badge.hide()

        self.role_box: QComboBox | None = None
        texts = QVBoxLayout()
        texts.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.name)
        top.addWidget(self.me_badge)
        top.addStretch()
        texts.addLayout(top)
        if editable_role:
            # Los roles enemigos no siempre se conocen: se pueden cambiar o dejar en "?".
            self.role_box = QComboBox()
            self.role_box.addItem("Rol ?", None)
            for r in Role:
                self.role_box.addItem(r.label, r)
            self.role_box.setCurrentIndex(self.role_box.findData(role))
            self.role_box.currentIndexChanged.connect(lambda _: self.role_changed.emit(self))
            texts.addWidget(self.role_box)
        else:
            texts.addWidget(self.detail)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)
        layout.addWidget(self.portrait)
        layout.addLayout(texts, 1)
        self.refresh()

    # --- Estado ------------------------------------------------------------

    @property
    def role(self) -> Role | None:
        return combo_role(self.role_box) if self.role_box else self._role

    def set_champion(self, champion_id: str | None, name: str | None, tentative: bool = False) -> None:
        """``tentative``: campeón solo «en hover» en el cliente, aún sin confirmar."""
        self.champion_id = champion_id
        self.champion_name = name
        self.tentative = tentative and champion_id is not None
        self.refresh()

    def set_role(self, role: Role | None) -> None:
        """Cambia el rol editable sin emitir role_changed (lo usa el draft en vivo)."""
        if self.role_box is not None:
            self.role_box.blockSignals(True)
            self.role_box.setCurrentIndex(self.role_box.findData(role))
            self.role_box.blockSignals(False)

    def set_me(self, is_me: bool) -> None:
        self._is_me = is_me
        self.me_badge.setVisible(is_me)
        self.setProperty("me", is_me)
        repolish(self)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        repolish(self)
        self.refresh()

    def refresh(self) -> None:
        self.portrait.setPixmap(self._portraits.get(self.champion_id, PORTRAIT))
        active = bool(self.property("active"))
        if self.champion_id:
            self.name.setText(self.champion_name or self.champion_id)
        else:
            self.name.setText("Eligiendo…" if active else "Vacío")
        self.detail.setText(f"{self._role.label} · sin confirmar" if self.tentative else self._role.label)
        state = "seleccionada" if active else ""
        tentative = "sin confirmar" if self.tentative else ""
        self.setAccessibleName(f"{self._role.label}: {self.champion_name or 'vacío'} {tentative} {state}".strip())

    # --- Eventos -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.cleared.emit(self)
        else:
            self.setFocus()
            self.activated.emit(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit(self)
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.cleared.emit(self)
        else:
            super().keyPressEvent(event)
