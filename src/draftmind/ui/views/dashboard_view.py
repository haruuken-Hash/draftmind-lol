"""Pantalla de inicio: bienvenida, accesos rápidos, cifras y estado de los datos."""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from draftmind.analysis.champion_stats import champion_performance, recent_form, valid_matches
from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import ConfidenceLevel, EvidenceKind
from draftmind.ui import theme
from draftmind.ui.components.visuals import HeroBanner, add_shadow, form_row, stat_tile
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.session import AppSession
from draftmind.ui.widgets import RIOT_DISCLAIMER, RIOT_DISCLAIMER_ES, card, notice_label, section_label

DEFAULT_SPLASH = "Ahri"


def _card(title: str, body: QLabel) -> QWidget:
    frame, layout = card()
    layout.addWidget(section_label(title))
    body.setWordWrap(True)
    body.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(body)
    layout.addStretch()
    return frame


class DashboardView(QWidget):
    open_draft = Signal()
    open_profile = Signal()

    def __init__(self, ctx: AppContext, session: AppSession, portraits: PortraitProvider,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._ctx = ctx
        self.session = session
        self.portraits = portraits

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        self.hero = HeroBanner(230)
        add_shadow(self.hero)
        self.hero_title = QLabel("Bienvenido a DraftMind")
        self.hero_title.setObjectName("heroTitle")
        self.hero_sub = QLabel("Estudia tus drafts y tus partidas con datos oficiales y explicaciones honestas.")
        self.hero_sub.setObjectName("heroSub")
        self.hero_sub.setWordWrap(True)
        draft_button = QPushButton("Abrir el tablero de draft")
        draft_button.setObjectName("primary")
        draft_button.clicked.connect(self.open_draft.emit)
        profile_button = QPushButton("Ver mi perfil")
        profile_button.clicked.connect(self.open_profile.emit)
        buttons = QHBoxLayout()
        buttons.addWidget(draft_button)
        buttons.addWidget(profile_button)
        buttons.addStretch()
        self.hero.content.addWidget(self.hero_title)
        self.hero.content.addWidget(self.hero_sub)
        self.hero.content.addStretch()
        self.form_holder = QVBoxLayout()
        self.hero.content.addLayout(self.form_holder)
        self.hero.content.addLayout(buttons)
        layout.addWidget(self.hero)

        if ctx.settings.demo_mode:
            layout.addWidget(notice_label(
                "Modo demostración: no hay API key de Riot. Historial y perfil usan partidas ficticias."
            ))

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tiles: dict[str, QLabel] = {}
        for key, caption in (("games", "Partidas analizadas"), ("winrate", "Win rate"),
                             ("main", "Campeón más jugado"), ("score", "Puntuación media")):
            frame, value = stat_tile("—", caption)
            self.tiles[key] = value
            tiles.addWidget(frame)
        layout.addLayout(tiles)

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
        grid.addWidget(_card("Tus preferencias", self.profile_label), 0, 1)
        grid.addWidget(_card("Cómo leer las recomendaciones", guide), 1, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch()
        legal = QLabel(f"{RIOT_DISCLAIMER}<br><i>{RIOT_DISCLAIMER_ES}</i>")
        legal.setWordWrap(True)
        legal.setStyleSheet(f"color: {theme.MUTED}; font-size: 8.5pt;")
        layout.addWidget(legal)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        session.matches_changed.connect(self.refresh_matches)
        self.refresh_profile()
        self.set_data_status("")
        self.refresh_matches()

    def refresh_matches(self) -> None:
        matches = self.session.matches
        valid = valid_matches(matches)
        champions = champion_performance(matches)
        names = {c.id: c.name for c in self._ctx.catalog.champions}
        account = self.session.account
        demo = self.session.matches_are_demo
        if account and not demo:
            self.hero_title.setText(f"Hola, {escape(account.game_name)}")
        wins = sum(1 for m in valid if m.win)
        scores = [m.performance_score for m in valid if m.performance_score is not None]
        suffix = " (demo)" if demo else ""
        self.tiles["games"].setText(f"{len(valid)}{suffix}")
        self.tiles["winrate"].setText(f"{wins / len(valid):.0%}" if valid else "—")
        self.tiles["main"].setText(names.get(champions[0].champion_id, champions[0].champion_id)
                                   if champions else "—")
        self.tiles["score"].setText(f"{sum(scores) / len(scores):.1f}" if scores else "—")
        while self.form_holder.count():
            widget = self.form_holder.takeAt(0).widget()
            if widget:
                widget.setParent(None)
        results = recent_form(matches, 10)
        if results:
            self.form_holder.addWidget(form_row(results))
        main = champions[0].champion_id if champions else DEFAULT_SPLASH
        self.portraits.load_splash(main, self.hero.set_image)

    def set_data_status(self, status: str) -> None:
        catalog = self._ctx.catalog
        demo = self._ctx.dataset.source
        if catalog.from_data_dragon:
            static = (f"Data Dragon <b>{escape(catalog.version or '')}</b> ({escape(catalog.language or '')}), "
                      f"{len(catalog.champions)} campeones")
        else:
            static = "Data Dragon: todavía no descargado"
        self.data_label.setText(
            f"{static}<br>{escape(demo.name)}: {len(self._ctx.dataset.champions)} perfiles editoriales"
            + (f"<br><span style='color:{theme.MUTED}'>{escape(status)}</span>" if status else "")
        )

    def refresh_profile(self) -> None:
        p = self._ctx.analyzer.profile
        names = {c.id: c.name for c in self._ctx.catalog.champions}
        favorites = ", ".join(names.get(i, i) for i in p.favorite_champions) or "ninguno"
        roles = ", ".join(r.label for r in p.main_roles) or "sin indicar"
        self.profile_label.setText(
            f"Nivel declarado: {p.experience.label}<br>Posiciones: {escape(roles)}<br>"
            f"Preferidos: {escape(favorites)}<br>"
            f"<span style='color:{theme.MUTED}'>Edítalo en «Configuración».</span>"
        )

    def on_catalog_changed(self) -> None:
        self.refresh_matches()
