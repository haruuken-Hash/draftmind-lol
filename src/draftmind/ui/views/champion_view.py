"""Explorador de campeones: cuadrícula de retratos, ficha y editor de perfiles.

Cada campeón tiene un perfil cualitativo con uno de tres orígenes:
estimación automática, perfil editorial de demostración o revisado por ti.
Al guardar una revisión, el análisis de toda la app pasa a usarla.
"""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import DamageType, ProfileOrigin, Role
from draftmind.domain.models import ChampionProfile
from draftmind.ui import theme
from draftmind.ui.components.champion_grid import ChampionGrid
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.widgets import TAG_LABELS, card, page_layout, subtitle_label, title_label

ATTRIBUTES = [
    ("engage", "Iniciación", 0),
    ("disengage", "Desenganche", 0),
    ("cc", "Control de masas", 0),
    ("early", "Presión temprana", 0),
    ("scaling", "Escalado", 0),
    ("frontline", "Primera línea", 0),
    ("difficulty", "Dificultad", 1),
    ("resource_dependence", "Dependencia de recursos", 0),
]


class ChampionView(QWidget):
    profiles_changed = Signal()

    def __init__(self, ctx: AppContext, portraits: PortraitProvider, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self._portraits = portraits
        self.current_id: str | None = None
        layout = page_layout(self)
        layout.addWidget(title_label("Campeones"))
        self.source_label = subtitle_label("")
        layout.addWidget(self.source_label)

        self.grid = ChampionGrid(ctx, portraits)

        detail, detail_layout = card()
        self.portrait = QLabel()
        self.name = QLabel()
        self.name.setStyleSheet("font-size: 15pt; font-weight: 700;")
        self.subtitle = QLabel()
        self.subtitle.setWordWrap(True)
        self.subtitle.setStyleSheet(f"color: {theme.MUTED};")
        head = QHBoxLayout()
        head.addWidget(self.portrait)
        names = QVBoxLayout()
        names.addWidget(self.name)
        names.addWidget(self.subtitle)
        head.addLayout(names, 1)
        detail_layout.addLayout(head)

        self.origin_label = QLabel()
        self.origin_label.setWordWrap(True)
        self.origin_label.setTextFormat(Qt.TextFormat.RichText)
        detail_layout.addWidget(self.origin_label)

        # --- Modo lectura: barras ---
        self.read_panel = QWidget()
        read_layout = QVBoxLayout(self.read_panel)
        read_layout.setContentsMargins(0, 0, 0, 0)
        self.bars: dict[str, QProgressBar] = {}
        for attr, label, minimum in ATTRIBUTES:
            bar = QProgressBar()
            bar.setRange(minimum, 3)
            bar.setFormat("%v/3")
            self.bars[attr] = bar
            read_layout.addWidget(QLabel(label))
            read_layout.addWidget(bar)
        detail_layout.addWidget(self.read_panel)

        # --- Modo edición ---
        self.edit_panel = QWidget()
        edit_layout = QGridLayout(self.edit_panel)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        self.spins: dict[str, QSpinBox] = {}
        for row, (attr, label, minimum) in enumerate(ATTRIBUTES):
            spin = QSpinBox()
            spin.setRange(minimum, 3)
            spin.setAccessibleName(label)
            self.spins[attr] = spin
            edit_layout.addWidget(QLabel(label), row, 0)
            edit_layout.addWidget(spin, row, 1)
        row = len(ATTRIBUTES)
        self.damage = QComboBox()
        for d in DamageType:
            self.damage.addItem(d.label, d.value)
        edit_layout.addWidget(QLabel("Tipo de daño"), row, 0)
        edit_layout.addWidget(self.damage, row, 1)
        roles_box = QWidget()
        roles_layout = QGridLayout(roles_box)
        roles_layout.setContentsMargins(0, 0, 0, 0)
        self.role_checks: dict[Role, QCheckBox] = {}
        for i, r in enumerate(Role):
            check = QCheckBox(r.label)
            self.role_checks[r] = check
            roles_layout.addWidget(check, i // 2, i % 2)
        edit_layout.addWidget(QLabel("Posiciones"), row + 1, 0, Qt.AlignmentFlag.AlignTop)
        edit_layout.addWidget(roles_box, row + 1, 1)
        self.edit_panel.hide()
        detail_layout.addWidget(self.edit_panel)

        # --- Botones ---
        self.edit_button = QPushButton("Revisar perfil")
        self.save_button = QPushButton("Guardar")
        self.save_button.setObjectName("primary")
        self.cancel_button = QPushButton("Cancelar")
        self.reset_button = QPushButton("Restablecer")
        self.reset_button.setToolTip("Borra tu revisión y vuelve al perfil editorial o estimado.")
        buttons = QHBoxLayout()
        for b in (self.edit_button, self.save_button, self.cancel_button, self.reset_button):
            buttons.addWidget(b)
        buttons.addStretch()
        detail_layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setWordWrap(True)
        detail_layout.addWidget(self.status)
        detail_layout.addStretch()

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        detail_scroll.setWidget(detail)
        detail_scroll.setFixedWidth(360)

        body = QHBoxLayout()
        body.addWidget(self.grid, 1)
        body.addWidget(detail_scroll)
        layout.addLayout(body, 1)

        self.grid.champion_selected.connect(self.show_champion)
        self.grid.champion_chosen.connect(self.show_champion)
        self.edit_button.clicked.connect(lambda: self.set_editing(True))
        self.cancel_button.clicked.connect(lambda: self.set_editing(False))
        self.save_button.clicked.connect(self.save_profile)
        self.reset_button.clicked.connect(self.reset_profile)
        self.on_catalog_changed()

    # --- Datos ---------------------------------------------------------------

    def on_catalog_changed(self) -> None:
        catalog = self._ctx.catalog
        origins = [p.origin for p in self._ctx.analyzer.champions]
        counts = {o: origins.count(o) for o in ProfileOrigin}
        if catalog.from_data_dragon:
            self.source_label.setText(
                f"{len(catalog.champions)} campeones de Data Dragon {catalog.version}. Perfiles: "
                f"{counts[ProfileOrigin.USER]} revisados por ti, {counts[ProfileOrigin.EDITORIAL]} editoriales y "
                f"{counts[ProfileOrigin.ESTIMATED]} estimados automáticamente. Son valoraciones 0-3, no estadísticas."
            )
        else:
            self.source_label.setText(
                "Sin datos de Data Dragon todavía: solo están los campeones de demostración."
            )
        self.grid.reload()
        if self.current_id is None and catalog.champions:
            self.current_id = catalog.champions[0].id
        if self.current_id:
            self.show_champion(self.current_id)

    def show_champion(self, champion_id: str) -> None:
        info = next((c for c in self._ctx.catalog.champions if c.id == champion_id), None)
        if info is None:
            return
        self.current_id = champion_id
        self.set_editing(False)
        self.status.clear()
        self.portrait.setPixmap(self._portraits.get(champion_id, 72))
        self.name.setText(escape(info.name))
        tags = ", ".join(TAG_LABELS.get(t, t) for t in info.tags)
        self.subtitle.setText(escape(" · ".join(x for x in (info.title, tags) if x)))

        analyzer = self._ctx.analyzer
        profile = analyzer.champion(champion_id) if analyzer.has_profile(champion_id) else None
        official = ""
        if info.attack is not None:
            official = (f"<br><span style='color:{theme.MUTED}'>Valoración oficial (0-10): ataque {info.attack}, "
                        f"defensa {info.defense}, magia {info.magic}, dificultad {info.difficulty}.</span>")
        if profile is None:
            self.origin_label.setText("<i>Sin perfil: hacen falta los datos de Data Dragon.</i>" + official)
            self.read_panel.hide()
            self.edit_button.setEnabled(False)
            self.reset_button.setVisible(False)
            return
        roles = ", ".join(r.label for r in profile.roles) or "sin posiciones estimadas"
        if profile.roles_observed:
            roles += (f" <span style='color:{theme.MUTED}'>(observadas en {profile.roles_observed} "
                      "apariciones en tus partidas descargadas)</span>")
        warning = ""
        if profile.origin is ProfileOrigin.ESTIMATED:
            warning = (f"<br><span style='color:{theme.WARNING}'>Calculado con reglas a partir de la clase y la "
                       "valoración oficial. Revísalo si conoces al campeón.</span>")
        self.origin_label.setText(
            f"<b>{profile.origin.label}</b>{warning}<br><b>Posiciones:</b> {roles} · "
            f"<b>Daño:</b> {profile.damage_type.label}{official}"
        )
        for attr, bar in self.bars.items():
            bar.setValue(getattr(profile, attr))
        self.read_panel.show()
        self.edit_button.setEnabled(True)
        self.reset_button.setVisible(profile.origin is ProfileOrigin.USER)

    # --- Edición -------------------------------------------------------------

    def set_editing(self, editing: bool) -> None:
        analyzer = self._ctx.analyzer
        if editing and self.current_id and analyzer.has_profile(self.current_id):
            profile = analyzer.champion(self.current_id)
            for attr, spin in self.spins.items():
                spin.setValue(getattr(profile, attr))
            self.damage.setCurrentIndex(self.damage.findData(profile.damage_type.value))
            for r, check in self.role_checks.items():
                check.setChecked(r in profile.roles)
        self.edit_panel.setVisible(editing)
        self.read_panel.setVisible(not editing and bool(self.current_id) and analyzer.has_profile(self.current_id))
        self.save_button.setVisible(editing)
        self.cancel_button.setVisible(editing)
        self.edit_button.setVisible(not editing)

    def edited_profile(self) -> ChampionProfile:
        base = self._ctx.analyzer.champion(self.current_id)
        return base.model_copy(update={
            **{attr: spin.value() for attr, spin in self.spins.items()},
            "damage_type": DamageType(self.damage.currentData()),
            "roles": [r for r, check in self.role_checks.items() if check.isChecked()],
            "origin": ProfileOrigin.USER,
        })

    def save_profile(self) -> None:
        profile = self.edited_profile()
        if not profile.roles:
            self.status.setText("Marca al menos una posición.")
            return
        self._ctx.champion_profiles.save(profile)
        self._ctx.rebuild_profiles()
        self.show_champion(profile.id)
        self.status.setText("Perfil guardado: el análisis ya usa tu revisión.")
        self.profiles_changed.emit()

    def reset_profile(self) -> None:
        if self.current_id is None:
            return
        if QMessageBox.question(self, "Restablecer perfil", "¿Borrar tu revisión de este campeón?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._ctx.champion_profiles.delete(self.current_id)
        self._ctx.rebuild_profiles()
        self.show_champion(self.current_id)
        self.status.setText("Revisión borrada.")
        self.profiles_changed.emit()
