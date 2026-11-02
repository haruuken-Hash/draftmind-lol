"""Ventana principal: barra lateral, pila de pantallas y descarga de Data Dragon."""

import logging
from functools import partial

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from draftmind.analysis.matchup_analyzer import patch_of
from draftmind.app.bootstrap import AppContext
from draftmind.integrations.data_dragon import DataDragonError
from draftmind.services.catalog_service import RefreshResult, demo_catalog
from draftmind.ui.components.visuals import glyph_icon
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.views.profile_view import ProfileView
from draftmind.ui.session import AppSession
from draftmind.ui.theme import STYLESHEET
from draftmind.ui.views.builds_view import BuildsView
from draftmind.ui.views.champion_view import ChampionView
from draftmind.ui.views.counters_view import CountersView
from draftmind.ui.views.dashboard_view import DashboardView
from draftmind.ui.views.draft_view import DraftView
from draftmind.ui.views.match_analysis_view import MatchAnalysisView
from draftmind.ui.views.match_history_view import MatchHistoryView
from draftmind.ui.views.research_view import ResearchView
from draftmind.ui.views.settings_view import SettingsView
from draftmind.ui.views.strategy_view import StrategyView
from draftmind.ui.workers import run_task

log = logging.getLogger(__name__)


def _logo_pixmap(size: int) -> QPixmap:
    """Logotipo propio: rombo con degradado y las iniciales «DM»."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor("#2ee6c4"))
    gradient.setColorAt(1, QColor("#3b82f6"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(1, 1, size - 2, size - 2), size * 0.28, size * 0.28)
    painter.fillPath(path, gradient)
    font = QFont("Segoe UI", int(size * 0.32))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#04110e"))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "DM")
    painter.end()
    return pixmap


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.session = AppSession()
        self.portraits = PortraitProvider(ctx)
        self._refreshing = False
        self.setWindowTitle("DraftMind LoL")
        self.setStyleSheet(STYLESHEET)
        self.resize(1360, 860)
        self.setMinimumSize(1100, 680)

        # Las partidas alimentan las estadísticas personales.
        self.session.matches_changed.connect(self._on_matches_changed)

        self.dashboard = DashboardView(ctx, self.session, self.portraits)
        self.champions_view = ChampionView(ctx, self.portraits)
        self.draft_view = DraftView(ctx, self.session, self.portraits)
        self.history_view = MatchHistoryView(ctx, self.session, self.portraits)
        self.counters_view = CountersView(ctx, self.session, self.portraits)
        self.builds_view = BuildsView(ctx, self.session, self.portraits)
        self.strategy_view = StrategyView(ctx, self.session)
        self.analysis_view = MatchAnalysisView(ctx, self.session, self.portraits)
        self.research_view = ResearchView(ctx)
        self.settings_view = SettingsView(ctx)
        self.profile_view = ProfileView(ctx, self.session, self.portraits)

        sections: list[tuple[str, str, QWidget]] = [
            ("home", "Inicio", self.dashboard),
            ("profile", "Mi perfil", self.profile_view),
            ("champions", "Campeones", self.champions_view),
            ("draft", "Draft", self.draft_view),
            ("counters", "Counters", self.counters_view),
            ("builds", "Runas y builds", self.builds_view),
            ("strategy", "Estrategia", self.strategy_view),
            ("history", "Historial", self.history_view),
            ("analysis", "Análisis postpartida", self.analysis_view),
            ("research", "Investigación", self.research_view),
            ("settings", "Configuración", self.settings_view),
        ]
        self._catalog_views = [self.champions_view, self.draft_view, self.history_view, self.counters_view,
                               self.builds_view, self.strategy_view, self.analysis_view, self.profile_view,
                               self.dashboard]

        # --- Barra lateral ---
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(236)
        logo = QLabel()
        logo.setPixmap(_logo_pixmap(34))
        brand = QLabel("DraftMind")
        brand.setObjectName("brand")
        brand_sub = QLabel("Asistente de estudio para LoL")
        brand_sub.setObjectName("brandSub")
        brand_texts = QVBoxLayout()
        brand_texts.setSpacing(0)
        brand_texts.addWidget(brand)
        brand_texts.addWidget(brand_sub)
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(18, 20, 12, 16)
        brand_row.setSpacing(10)
        brand_row.addWidget(logo)
        brand_row.addLayout(brand_texts, 1)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 10)
        side_layout.addLayout(brand_row)
        side_layout.addWidget(self.nav, 1)
        self.account_label = QLabel()
        self.account_label.setObjectName("brandSub")
        self.account_label.setWordWrap(True)
        self.account_label.setContentsMargins(20, 0, 12, 0)
        side_layout.addWidget(self.account_label)

        self.stack = QStackedWidget()
        for index, (icon, name, view) in enumerate(sections):
            item = QListWidgetItem(glyph_icon(icon), name)
            self.nav.addItem(item)
            self.stack.addWidget(view)
            # Ctrl+1 … Ctrl+9 y Ctrl+0 saltan a las diez primeras secciones.
            if index < 10:
                key = f"Ctrl+{(index + 1) % 10}"
                QShortcut(QKeySequence(key), self, activated=partial(self.nav.setCurrentRow, index))
                item.setToolTip(key)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # --- Barra de estado ---
        mode = "Modo demostración" if ctx.settings.demo_mode else "API key de Riot configurada"
        self.status_mode = QLabel(mode)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().addPermanentWidget(self.status_mode)

        # --- Conexiones entre pantallas ---
        self.dashboard.open_draft.connect(lambda: self.go_to(self.draft_view))
        self.dashboard.open_profile.connect(lambda: self.go_to(self.profile_view))
        self.strategy_view.open_draft.connect(lambda: self.go_to(self.draft_view))
        self.history_view.open_match.connect(lambda _: self.go_to(self.analysis_view))
        self.profile_view.open_history.connect(lambda: self.go_to(self.history_view))
        self.settings_view.profile_saved.connect(self.dashboard.refresh_profile)
        self.settings_view.profile_saved.connect(self.draft_view.on_profile_changed)
        self.settings_view.profile_saved.connect(self.counters_view.refresh)
        self.settings_view.refresh_requested.connect(self.refresh_data)
        self.settings_view.clear_cache_requested.connect(self.clear_cache)
        self.settings_view.stats_changed.connect(self._on_stats_changed)
        self.settings_view.matches_cleared.connect(self.history_view.load_demo)
        self.settings_view.live_settings_changed.connect(self.draft_view.configure_live)
        self.champions_view.profiles_changed.connect(self._on_profiles_changed)

        self._on_matches_changed()
        if ctx.settings.ddragon_enabled:
            self.refresh_data()

    def go_to(self, view: QWidget) -> None:
        self.nav.setCurrentRow(self.stack.indexOf(view))

    # --- Estadísticas personales ------------------------------------------------

    def _on_matches_changed(self) -> None:
        account = self.session.account
        if hasattr(self, "account_label"):
            demo = " (demostración)" if self.session.matches_are_demo else ""
            self.account_label.setText(f"{account.riot_id}{demo}" if account else "")
        self.ctx.stats.set_matches(self.session.matches, self.session.matches_are_demo,
                                   account.platform if account else None)
        # Las partidas descargadas corrigen las posiciones de los perfiles estimados.
        self.ctx.rebuild_profiles()
        if hasattr(self, "strategy_view"):
            self._on_profiles_changed()
        self._on_stats_changed()
        self._download_item_icons()

    def _download_item_icons(self) -> None:
        """Iconos de los objetos de tus partidas que aún no estén en caché (componentes, botas...)."""
        data = self.ctx.game_data
        if data is None or getattr(self, "_icons_busy", False):
            return
        client = self.ctx.catalogs.client
        missing = {i for m in self.session.matches for i in m.items
                   if client.cached_image(f"{data.version}/img/item/{i}.png") is None}
        if not missing:
            return
        self._icons_busy = True

        def work() -> None:
            for item_id in missing:
                try:
                    client.item_image(data.version, f"{item_id}.png")
                except DataDragonError:
                    pass  # Si no existe en esta versión, se sigue mostrando el número.

        def done(_) -> None:
            self._icons_busy = False
            self.portraits.invalidate()
            if hasattr(self, "analysis_view"):
                self.history_view.apply_filters()
                self.analysis_view.refresh()

        run_task(work, on_done=done, on_error=lambda _: setattr(self, "_icons_busy", False))

    def _on_stats_changed(self) -> None:
        # El Historial carga partidas al construirse, antes de que existan las
        # vistas creadas después de él; por eso se comprueba cada una.
        if hasattr(self, "draft_view"):
            self.draft_view.update_analysis()
        if hasattr(self, "counters_view"):
            self.counters_view.refresh()
        if hasattr(self, "settings_view"):
            self.settings_view.update_stats_info()

    def _on_profiles_changed(self) -> None:
        """Un perfil revisado afecta al draft, counters, builds y estrategia."""
        if self.champions_view.current_id:
            self.champions_view.show_champion(self.champions_view.current_id)
        self.draft_view.grid.reload()
        self.draft_view.update_analysis()
        self.counters_view.refresh()
        self.builds_view.refresh()
        self.strategy_view.refresh()

    # --- Data Dragon -------------------------------------------------------

    def refresh_data(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self._set_status("Buscando datos de Data Dragon…", busy=True)
        self.progress.setRange(0, 0)  # Indeterminado hasta conocer el total.
        self.progress.show()
        run_task(
            self.ctx.catalogs.refresh,
            on_done=self._on_refresh_done,
            on_error=self._on_refresh_failed,
            on_progress=self._on_refresh_progress,
        )

    def _on_refresh_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress.setFormat(f"Imágenes {done}/{total}")

    def _on_refresh_done(self, result: RefreshResult) -> None:
        self._refreshing = False
        self.progress.hide()
        changed = (result.catalog.version, result.catalog.language) != (
            self.ctx.catalog.version, self.ctx.catalog.language
        )
        self.ctx.catalog = result.catalog
        if result.game_data is not None:
            self.ctx.game_data = result.game_data
        self.ctx.analyzer.current_patch = patch_of(result.catalog.version)
        self.portraits.invalidate()
        self._notify_catalog_changed()
        self._download_item_icons()
        message = f"Datos actualizados: Data Dragon {result.catalog.version}."
        if not changed:
            message = f"Data Dragon {result.catalog.version}: ya estaba al día."
        self._set_status(" ".join([message] + result.warnings))

    def _on_refresh_failed(self, error: str) -> None:
        self._refreshing = False
        self.progress.hide()
        log.warning("Fallo al actualizar Data Dragon: %s", error)
        fallback = "se usan los datos guardados." if self.ctx.catalog.from_data_dragon else "se usan los datos de demostración."
        self._set_status(f"No se pudo actualizar Data Dragon ({error}); {fallback}")

    def clear_cache(self) -> None:
        answer = QMessageBox.question(
            self, "Borrar caché",
            "Se borrarán los datos e imágenes descargados de Data Dragon. Podrás volver a descargarlos. ¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.ctx.catalogs.client.clear_cache()
        except OSError as exc:
            self._set_status(f"No se pudo borrar la caché: {exc}")
            return
        self.ctx.catalog = demo_catalog(self.ctx.dataset)
        self.ctx.game_data = None
        self.portraits.invalidate()
        self._notify_catalog_changed()
        self._set_status("Caché borrada. Pulsa «Buscar actualizaciones» para descargar de nuevo.")

    def _notify_catalog_changed(self) -> None:
        self.ctx.rebuild_profiles()  # Nuevos campeones de Data Dragon = nuevas estimaciones.
        for view in self._catalog_views:
            view.on_catalog_changed()
        self.dashboard.refresh_profile()

    def _set_status(self, text: str, busy: bool = False) -> None:
        self.statusBar().showMessage(text)
        self.dashboard.set_data_status(text)
        self.settings_view.update_ddragon_info(text, busy=busy)
