"""Mi perfil: rango, maestría y estadísticas personales (al estilo de OP.GG).

Rango y maestría salen de la Riot API (league-v4 y champion-mastery-v4); el
resto se calcula con tus partidas descargadas. Sin API key se muestran las
partidas FICTICIAS de demostración y se indica así.
"""

from html import escape

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from draftmind.analysis.champion_stats import champion_performance, recent_form, role_distribution, valid_matches
from draftmind.analysis.postgame_analyzer import averages
from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import Role
from draftmind.ui import theme
from draftmind.ui.components.visuals import HeroBanner, add_shadow, form_row, rank_pill, stat_tile
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.session import AppSession
from draftmind.ui.views.match_history_view import NumericItem
from draftmind.ui.widgets import card, notice_label, section_label
from draftmind.ui.workers import run_task

TABLE_COLUMNS = ["Campeón", "Partidas", "V - D", "Win rate", "KDA", "CS/min", "Puntuación", "MVP/ACE"]


class ProfileView(QWidget):
    open_history = Signal()

    def __init__(self, ctx: AppContext, session: AppSession, portraits: PortraitProvider,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.portraits = portraits
        self._fetched_for: str | None = None

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # --- Cabecera con ilustración ---
        self.hero = HeroBanner(200)
        add_shadow(self.hero)
        self.hero_title = QLabel()
        self.hero_title.setObjectName("heroTitle")
        self.hero_sub = QLabel()
        self.hero_sub.setObjectName("heroSub")
        self.rank_row = QHBoxLayout()
        self.rank_row.setSpacing(10)
        self.refresh_button = QPushButton("Actualizar rango y maestría")
        self.refresh_button.setObjectName("primary")
        self.refresh_button.clicked.connect(self.fetch_player_profile)
        top = QHBoxLayout()
        top.addWidget(self.hero_title)
        top.addStretch()
        top.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        self.hero.content.addLayout(top)
        self.hero.content.addWidget(self.hero_sub)
        self.hero.content.addStretch()
        self.hero.content.addLayout(self.rank_row)
        layout.addWidget(self.hero)

        self.notice = notice_label("")
        layout.addWidget(self.notice)

        # --- Cifras ---
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tiles: dict[str, QLabel] = {}
        for key, caption in (("games", "Partidas"), ("winrate", "Win rate"), ("kda", "KDA medio"),
                             ("cs", "CS por minuto"), ("score", "Puntuación media"), ("badges", "MVP / ACE")):
            frame, value = stat_tile("—", caption)
            self.tiles[key] = value
            tiles.addWidget(frame)
        layout.addLayout(tiles)

        # --- Cuerpo en dos columnas ---
        body = QHBoxLayout()
        body.setSpacing(16)
        left = QVBoxLayout()
        left.addWidget(section_label("Tus campeones"))
        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(QSize(30, 30))
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(360)
        left.addWidget(self.table, 1)
        body.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(12)
        roles_card, roles_layout = card()
        roles_layout.addWidget(section_label("Posiciones"))
        self.role_bars: dict[Role, tuple[QLabel, QProgressBar]] = {}
        for role in Role:
            label = QLabel(role.label)
            bar = QProgressBar()
            bar.setRange(0, 100)
            row = QHBoxLayout()
            label.setFixedWidth(70)
            row.addWidget(label)
            row.addWidget(bar, 1)
            roles_layout.addLayout(row)
            self.role_bars[role] = (label, bar)
        right.addWidget(roles_card)

        mastery_card, mastery_layout = card()
        mastery_layout.addWidget(section_label("Maestría"))
        self.mastery_grid = QGridLayout()
        self.mastery_grid.setSpacing(8)
        self.mastery_grid.setColumnStretch(1, 1)  # El texto ocupa el resto, pegado al retrato.
        mastery_layout.addLayout(self.mastery_grid)
        right.addWidget(mastery_card)

        form_card, form_layout = card()
        form_layout.addWidget(section_label("Forma reciente"))
        self.form_holder = QVBoxLayout()
        form_layout.addLayout(self.form_holder)
        go_history = QPushButton("Ver historial completo")
        go_history.setObjectName("link")
        go_history.clicked.connect(self.open_history.emit)
        form_layout.addWidget(go_history)
        right.addWidget(form_card)
        right.addStretch()
        body.addLayout(right, 2)
        layout.addLayout(body, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        session.matches_changed.connect(self.refresh)
        session.player_profile_changed.connect(self.refresh)
        self.refresh()

    # --- Datos ---------------------------------------------------------------

    def fetch_player_profile(self) -> None:
        account = self.session.account
        if account is None or self.session.matches_are_demo or not self.ctx.matches.can_use_api:
            return
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Consultando…")
        self._fetched_for = account.puuid

        def done(profile) -> None:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Actualizar rango y maestría")
            fresh = self.ctx.matches.repository.get_account()
            if fresh and fresh.puuid != account.puuid:
                # Cambió la clave a la de otra aplicación: el PUUID y las partidas se actualizaron.
                self._fetched_for = fresh.puuid
                self.session.set_matches(fresh, self.ctx.matches.stored_matches(fresh.puuid), demo=False)
            self.session.set_player_profile(profile)

        def failed(error: str) -> None:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setText("Actualizar rango y maestría")
            self.notice.setText(f"<b>Aviso:</b> no se pudo consultar el rango: {escape(error)}")
            self.notice.show()

        run_task(lambda: self.ctx.matches.player_profile(account), on_done=done, on_error=failed)

    def refresh(self) -> None:
        account = self.session.account
        matches = self.session.matches
        names = {c.id: c.name for c in self.ctx.catalog.champions}
        demo = self.session.matches_are_demo
        can_api = self.ctx.matches.can_use_api and not demo

        # Al cargar una cuenta real por primera vez, se consulta el rango automáticamente.
        if can_api and account and self._fetched_for != account.puuid:
            self.fetch_player_profile()

        valid = valid_matches(matches)
        champions = champion_performance(matches)
        self.hero_title.setText(escape(account.riot_id) if account else "Sin cuenta vinculada")
        server = account.platform if account else "—"
        self.hero_sub.setText(f"Servidor {server} · {len(valid)} partidas analizadas"
                              + (" · DATOS FICTICIOS de demostración" if demo else ""))
        top = champions[0].champion_id if champions else None
        self.hero.set_image(None)
        self.portraits.load_splash(top, self.hero.set_image)

        self.refresh_button.setVisible(can_api)
        if demo:
            self.notice.setText("<b>Aviso:</b> partidas FICTICIAS de demostración. Configura tu API key y carga "
                                "tus partidas en «Historial» para ver tu perfil real.")
        self.notice.setVisible(demo)
        self._render_rank(can_api)

        # Cifras.
        wins = sum(1 for m in valid if m.win)
        avg = averages(valid)
        scores = [m.performance_score for m in valid if m.performance_score is not None]
        self.tiles["games"].setText(str(len(valid)))
        self.tiles["winrate"].setText(f"{wins / len(valid):.0%}" if valid else "—")
        self.tiles["kda"].setText(f"{avg['kda']:.2f}" if avg["kda"] is not None else "—")
        self.tiles["cs"].setText(f"{avg['cs_per_min']:.1f}" if avg["cs_per_min"] is not None else "—")
        self.tiles["score"].setText(f"{sum(scores) / len(scores):.1f}" if scores else "—")
        mvp = sum(1 for m in valid if m.badge == "MVP")
        ace = sum(1 for m in valid if m.badge == "ACE")
        self.tiles["badges"].setText(f"{mvp} / {ace}")

        # Tabla de campeones.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(champions))
        for row, c in enumerate(champions):
            wr_color = theme.WIN if c.win_rate >= 0.5 else theme.LOSS
            cells = [
                QTableWidgetItem(QIcon(self.portraits.get(c.champion_id, 30)), names.get(c.champion_id, c.champion_id)),
                NumericItem(str(c.games), c.games),
                QTableWidgetItem(f"{c.wins} - {c.games - c.wins}"),
                NumericItem(f"{c.win_rate:.0%}", c.win_rate),
                NumericItem("—" if c.kda is None else f"{c.kda:.2f}", c.kda),
                NumericItem("—" if c.cs_per_min is None else f"{c.cs_per_min:.1f}", c.cs_per_min),
                NumericItem("—" if c.avg_score is None else f"{c.avg_score:.1f}", c.avg_score),
                NumericItem(str(c.mvp_or_ace), c.mvp_or_ace),
            ]
            cells[3].setForeground(QBrush(QColor(wr_color)))
            for col, cell in enumerate(cells):
                self.table.setItem(row, col, cell)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.DescendingOrder)  # Más jugados primero.

        # Posiciones.
        distribution = role_distribution(matches)
        total = sum(distribution.values())
        for role, (label, bar) in self.role_bars.items():
            count = distribution.get(role, 0)
            bar.setValue(round(100 * count / total) if total else 0)
            bar.setFormat(f"{count} partidas")

        # Forma reciente.
        while self.form_holder.count():
            widget = self.form_holder.takeAt(0).widget()
            if widget:
                widget.setParent(None)
        results = recent_form(matches, 20)
        if results:
            self.form_holder.addWidget(form_row(results))
            wins_recent = sum(results)
            caption = QLabel(f"{wins_recent} V · {len(results) - wins_recent} D en las últimas {len(results)} "
                             "(más recientes a la izquierda)")
            caption.setStyleSheet(f"color: {theme.MUTED};")
            self.form_holder.addWidget(caption)

        self._render_mastery(names)

    def _render_rank(self, can_api: bool) -> None:
        while self.rank_row.count():
            widget = self.rank_row.takeAt(0).widget()
            if widget:
                widget.setParent(None)
        profile = self.session.player_profile
        if not can_api:
            info = QLabel("Rango no disponible sin API key." if not self.ctx.matches.can_use_api else
                          "Rango no disponible en modo demostración.")
            info.setObjectName("heroSub")
            self.rank_row.addWidget(info)
        elif profile is None:
            info = QLabel("Consultando rango…")
            info.setObjectName("heroSub")
            self.rank_row.addWidget(info)
        elif not profile.ranked:
            self.rank_row.addWidget(rank_pill("", "Sin clasificar esta temporada"))
        for entry in profile.ranked if (profile and can_api) else []:
            box = QVBoxLayout()
            box.setSpacing(2)
            pill = rank_pill(entry.tier, f"{entry.tier_label} · {entry.lp} LP")
            wr = entry.win_rate
            detail = QLabel(f"{entry.queue_label} · {entry.wins} V {entry.losses} D"
                            + (f" ({wr:.0%})" if wr is not None else "") + (" · en racha" if entry.hot_streak else ""))
            detail.setObjectName("heroSub")
            holder = QWidget()
            holder_layout = QVBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setSpacing(3)
            holder_layout.addWidget(pill, 0, Qt.AlignmentFlag.AlignLeft)
            holder_layout.addWidget(detail)
            self.rank_row.addWidget(holder)
        self.rank_row.addStretch()

    def _render_mastery(self, names: dict[str, str]) -> None:
        while self.mastery_grid.count():
            widget = self.mastery_grid.takeAt(0).widget()
            if widget:
                widget.setParent(None)
        profile = self.session.player_profile
        if not profile or not profile.masteries:
            info = QLabel("Disponible con tu API key y tus partidas reales.")
            info.setStyleSheet(f"color: {theme.MUTED};")
            self.mastery_grid.addWidget(info, 0, 0)
            return
        key_to_id = self.ctx.champion_keys()
        for i, m in enumerate(profile.masteries[:6]):
            champion_id = key_to_id.get(m.champion_key)
            portrait = QLabel()
            portrait.setPixmap(self.portraits.get(champion_id, 40))
            text = QLabel(f"<b>{escape(names.get(champion_id, str(m.champion_key)))}</b><br>"
                          f"<span style='color:{theme.MUTED}'>Nivel {m.level} · {m.points:,} pts</span>"
                          .replace(",", "."))
            self.mastery_grid.addWidget(portrait, i, 0)
            self.mastery_grid.addWidget(text, i, 1)

    def on_catalog_changed(self) -> None:
        self.refresh()
