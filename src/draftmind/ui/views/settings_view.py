"""Fuentes de datos, configuración y perfil personal."""

from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import ExperienceLevel, Role
from draftmind.domain.models import UserProfile
from draftmind.integrations.league_client import DEFAULT_INSTALL_DIR
from draftmind.services.live_draft_service import LiveDraftService
from draftmind.ui.widgets import RIOT_DISCLAIMER, RIOT_DISCLAIMER_ES, title_label
from draftmind.ui.workers import run_task


class SettingsView(QWidget):
    profile_saved = Signal()
    refresh_requested = Signal()
    clear_cache_requested = Signal()
    stats_changed = Signal()
    matches_cleared = Signal()
    live_settings_changed = Signal()

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title_label("Fuentes de datos y configuración"))
        layout.addWidget(self._sources_box())
        layout.addWidget(self._stats_box())
        layout.addWidget(self._live_box())
        layout.addWidget(self._profile_box())
        legal = QLabel(f"{RIOT_DISCLAIMER}<br><i>{RIOT_DISCLAIMER_ES}</i>")
        legal.setWordWrap(True)
        legal.setStyleSheet("color: #8b929c; font-size: 8.5pt;")
        layout.addWidget(legal)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self._load_profile()

    def _sources_box(self) -> QGroupBox:
        s = self._ctx.settings
        src = self._ctx.dataset.source
        key_state = (
            "Configurada (el valor no se muestra). Se usa en «Historial»."
            if s.has_riot_api_key
            else "No configurada: modo demostración."
        )
        box = QGroupBox("Fuentes y almacenamiento")
        form = QFormLayout(box)
        for label, value in [
            ("API key de Riot:", key_state),
            ("Perfiles de análisis:", f"{src.name} ({src.kind.label})"),
            ("Carpeta de datos:", str(s.data_dir)),
            ("Base de datos:", str(s.database_path)),
        ]:
            value_label = QLabel(escape(value))
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(label, value_label)

        self.ddragon_label = QLabel()
        self.ddragon_label.setWordWrap(True)
        self.ddragon_status = QLabel()
        self.ddragon_status.setWordWrap(True)
        self.refresh_button = QPushButton("Buscar actualizaciones")
        self.clear_cache_button = QPushButton("Borrar caché")
        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.clear_cache_button)
        buttons.addStretch()
        form.addRow("Data Dragon:", self.ddragon_label)
        form.addRow("", self.ddragon_status)
        form.addRow("", buttons)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.clear_cache_button.clicked.connect(self.clear_cache_requested.emit)
        self.update_ddragon_info()
        return box

    def _stats_box(self) -> QGroupBox:
        box = QGroupBox("Estadísticas y partidas")
        form = QFormLayout(box)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        import_button = QPushButton("Importar estadísticas (JSON)…")
        remove_button = QPushButton("Quitar importación")
        clear_matches = QPushButton("Borrar partidas guardadas")
        buttons = QHBoxLayout()
        for b in (import_button, remove_button, clear_matches):
            buttons.addWidget(b)
        buttons.addStretch()
        form.addRow("Fuentes activas:", self.stats_label)
        form.addRow("", buttons)
        hint = QLabel("Formato del archivo en docs/data_sources.md. Debe indicar la fuente, su URL, el parche y la "
                      "fecha de consulta. Importa solo datos cuyo uso permita la fuente.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8b929c;")
        form.addRow("", hint)
        import_button.clicked.connect(self._import_stats)
        remove_button.clicked.connect(self._remove_stats)
        clear_matches.clicked.connect(self._clear_matches)
        self.update_stats_info()
        return box

    def _live_box(self) -> QGroupBox:
        box = QGroupBox("Draft en vivo (cliente de LoL)")
        layout = QVBoxLayout(box)
        explanation = QLabel(
            "Lee la selección de campeones del cliente abierto y la refleja en «Draft». Solo lectura: "
            "nunca elige ni bloquea campeones, no muestra nombres de jugadores y se detiene durante la "
            "partida. Usa la League Client API, que Riot no soporta oficialmente: puede dejar de "
            "funcionar con un parche."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.live_enabled = QCheckBox("Activar el draft en vivo")
        self.live_enabled.setChecked(self._ctx.app_settings.live_draft_enabled)
        layout.addWidget(self.live_enabled)
        self.league_dir = QLineEdit(str(self._ctx.app_settings.league_install_dir))
        browse = QPushButton("Examinar…")
        test = QPushButton("Probar conexión")
        row = QHBoxLayout()
        row.addWidget(QLabel("Carpeta de League of Legends:"))
        row.addWidget(self.league_dir, 1)
        row.addWidget(browse)
        row.addWidget(test)
        layout.addLayout(row)
        self.live_test_status = QLabel()
        self.live_test_status.setWordWrap(True)
        layout.addWidget(self.live_test_status)

        self.live_enabled.toggled.connect(self._save_live_settings)
        self.league_dir.editingFinished.connect(self._save_live_settings)
        browse.clicked.connect(self._browse_league_dir)
        test.clicked.connect(self._test_live)
        return box

    def _save_live_settings(self) -> None:
        settings = self._ctx.app_settings
        settings.live_draft_enabled = self.live_enabled.isChecked()
        settings.league_install_dir = Path(self.league_dir.text().strip() or str(DEFAULT_INSTALL_DIR))
        self.live_settings_changed.emit()

    def _browse_league_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de League of Legends", self.league_dir.text())
        if folder:
            self.league_dir.setText(folder)
            self._save_live_settings()

    def _test_live(self) -> None:
        self.live_test_status.setText("Comprobando…")
        service = LiveDraftService(Path(self.league_dir.text().strip()), self._ctx.champion_keys)
        run_task(service.poll,
                 on_done=lambda status: self.live_test_status.setText(escape(status.message)),
                 on_error=lambda error: self.live_test_status.setText(f"Error: {escape(error)}"))

    def update_stats_info(self, message: str = "") -> None:
        stats = self._ctx.stats
        lines = []
        if stats.personal:
            lines.append(f"Tus partidas: {escape(stats.personal.source.name)}")
        if stats.imported:
            d = stats.imported.data
            lines.append(f"Importada: {escape(d.source.name)} · parche {escape(d.patch)} · {len(d.rows)} filas · "
                         f"consultada {d.source.retrieved_at:%d/%m/%Y}")
        if stats.import_error:
            lines.append(f"Error en el archivo importado: {escape(stats.import_error)}")
        lines.append(f"Partidas guardadas en local: {self._ctx.matches.repository.count()}")
        if message:
            lines.append(f"<b>{escape(message)}</b>")
        self.stats_label.setText("<br>".join(lines))

    def _import_stats(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar estadísticas", "", "JSON (*.json)")
        if not path:
            return
        try:
            provider = self._ctx.stats.import_file(Path(path))
        except Exception as exc:
            self.update_stats_info(f"No se importó: {exc}")
            return
        self.update_stats_info(f"Importadas {len(provider.data.rows)} filas de «{provider.name}».")
        self.stats_changed.emit()

    def _remove_stats(self) -> None:
        self._ctx.stats.remove_import()
        self.update_stats_info("Importación eliminada.")
        self.stats_changed.emit()

    def _clear_matches(self) -> None:
        if QMessageBox.question(self, "Borrar partidas", "Se borrarán las partidas descargadas de la Riot API. "
                                "Podrás volver a descargarlas. ¿Continuar?") != QMessageBox.StandardButton.Yes:
            return
        self._ctx.matches.repository.clear_matches()
        self.update_stats_info("Partidas guardadas borradas.")
        self.matches_cleared.emit()

    def update_ddragon_info(self, status: str | None = None, busy: bool = False) -> None:
        catalog = self._ctx.catalog
        size_mb = self._ctx.catalogs.client.cache_size_bytes() / 1_000_000
        if catalog.from_data_dragon:
            text = f"Versión {catalog.version} · idioma {catalog.language} · {len(catalog.champions)} campeones"
        else:
            text = "Sin datos descargados todavía."
        self.ddragon_label.setText(f"{escape(text)}<br>Caché: {size_mb:.1f} MB en {escape(str(self._ctx.settings.ddragon_cache_dir))}")
        if status is not None:
            self.ddragon_status.setText(escape(status))
        self.refresh_button.setEnabled(not busy and self._ctx.settings.ddragon_enabled)
        self.clear_cache_button.setEnabled(not busy)

    def _profile_box(self) -> QGroupBox:
        box = QGroupBox("Perfil personal")
        form = QFormLayout(box)

        self.experience = QComboBox()
        for level in ExperienceLevel:
            self.experience.addItem(level.label, level)
        form.addRow("Nivel autodeclarado:", self.experience)

        roles_row = QHBoxLayout()
        self.role_checks: dict[Role, QCheckBox] = {}
        for role in Role:
            check = QCheckBox(role.label)
            self.role_checks[role] = check
            roles_row.addWidget(check)
        roles_row.addStretch()
        form.addRow("Posiciones habituales:", roles_row)

        self.favorites = QListWidget()
        self.favorites.setMaximumHeight(180)
        for c in self._ctx.analyzer.champions:
            item = QListWidgetItem(c.name)
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.favorites.addItem(item)
        form.addRow("Campeones preferidos:", self.favorites)

        self.goals = QPlainTextEdit()
        self.goals.setPlaceholderText("Ej.: mejorar el farmeo, aprender a jugar jungla…")
        self.goals.setMaximumHeight(80)
        form.addRow("Objetivos de aprendizaje:", self.goals)

        save = QPushButton("Guardar perfil")
        save.setObjectName("primary")
        self.status = QLabel()
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(self.status, 1)
        form.addRow(row)
        save.clicked.connect(self.save_profile)
        return box

    def _load_profile(self) -> None:
        p = self._ctx.analyzer.profile
        self.experience.setCurrentIndex(self.experience.findData(p.experience))
        for role, check in self.role_checks.items():
            check.setChecked(role in p.main_roles)
        for i in range(self.favorites.count()):
            item = self.favorites.item(i)
            checked = item.data(Qt.ItemDataRole.UserRole) in p.favorite_champions
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.goals.setPlainText(p.learning_goals)

    def current_profile(self) -> UserProfile:
        favorites = [
            self.favorites.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.favorites.count())
            if self.favorites.item(i).checkState() == Qt.CheckState.Checked
        ]
        return UserProfile(
            favorite_champions=favorites,
            main_roles=[r for r, c in self.role_checks.items() if c.isChecked()],
            experience=ExperienceLevel(self.experience.currentData()),
            learning_goals=self.goals.toPlainText().strip(),
        )

    def save_profile(self) -> None:
        profile = self.current_profile()
        try:
            self._ctx.profiles.save(profile)
        except Exception as exc:  # Error de disco o de base de datos.
            self.status.setText(f"Error al guardar: {exc}")
            return
        self._ctx.analyzer.profile = profile
        self.status.setText("Perfil guardado.")
        self.profile_saved.emit()
