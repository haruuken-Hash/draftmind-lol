"""Historial de partidas propias (Riot API o demostración) con filtros."""

from html import escape

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from draftmind.analysis.postgame_analyzer import MatchFilter, cs_per_min, is_probable_remake, kda, kill_participation
from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import Role
from draftmind.domain.models import MatchSummary
from draftmind.integrations.riot_api import Platform, RiotApiError
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.session import AppSession
from draftmind.ui.widgets import card, combo_role, notice_label, page_layout, subtitle_label, title_label
from draftmind.ui.workers import run_task

COLUMNS = ["Fecha", "Resultado", "Campeón", "Posición", "Duración", "K / D / A", "KDA",
           "CS (por min)", "Oro", "Visión", "Daño a campeones", "Daño recibido", "Part. asesinatos", "Objetos"]
ITEM_ICON = 22


def fmt(value, pattern: str = "{}", missing: str = "—") -> str:
    return missing if value is None else pattern.format(value)


class NumericItem(QTableWidgetItem):
    """Celda que se ordena por su valor numérico y no por el texto."""

    def __init__(self, text: str, value: float | None):
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole, value if value is not None else float("-inf"))

    def __lt__(self, other):
        return self.data(Qt.ItemDataRole.UserRole) < other.data(Qt.ItemDataRole.UserRole)


class MatchHistoryView(QWidget):
    open_match = Signal(str)

    def __init__(self, ctx: AppContext, session: AppSession, portraits: PortraitProvider,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.portraits = portraits
        layout = page_layout(self)
        layout.addWidget(title_label("Historial"))
        layout.addWidget(subtitle_label(
            "Tus partidas mediante la API oficial de Riot. Se descargan solo las que falten y se "
            "guardan en local. Doble clic en una partida para analizarla."
        ))

        account_box, account_layout = card()
        self.riot_id = QLineEdit(placeholderText="Riot ID, p. ej. MiNombre#LAN")
        self.platform = QComboBox()
        for p in Platform:
            self.platform.addItem(p.label, p.value)
        self.platform.setCurrentIndex(self.platform.findData(Platform.LA1.value))
        self.count = QSpinBox()
        self.count.setRange(5, 50)
        self.count.setValue(20)
        self.count.setSuffix(" partidas")
        self.load_button = QPushButton("Cargar partidas")
        self.load_button.setObjectName("primary")
        self.demo_button = QPushButton("Ver demostración")
        row = QHBoxLayout()
        row.addWidget(self.riot_id, 2)
        row.addWidget(self.platform, 2)
        row.addWidget(self.count)
        row.addWidget(self.load_button)
        row.addWidget(self.demo_button)
        account_layout.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        account_layout.addWidget(self.status)
        if not ctx.matches.can_use_api:
            account_layout.addWidget(notice_label(
                "No hay API key de Riot: se muestran partidas FICTICIAS de demostración. "
                "Para ver las tuyas, configura RIOT_API_KEY en el archivo .env (ver docs/riot_api_setup.md)."
            ))
            for w in (self.riot_id, self.platform, self.count, self.load_button):
                w.setEnabled(False)
        layout.addWidget(account_box)

        self.champion_filter = QComboBox()
        self.role_filter = QComboBox()
        self.role_filter.addItem("Todas las posiciones", None)
        for r in Role:
            self.role_filter.addItem(r.label, r)
        self.period_filter = QComboBox()
        for label, days in (("Todo el periodo", None), ("Últimos 7 días", 7), ("Últimos 30 días", 30)):
            self.period_filter.addItem(label, days)
        self.result_filter = QComboBox()
        for label, value in (("Victorias y derrotas", None), ("Solo victorias", True), ("Solo derrotas", False)):
            self.result_filter.addItem(label, value)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Filtrar:"))
        for w in (self.champion_filter, self.role_filter, self.period_filter, self.result_filter):
            filters.addWidget(w)
        filters.addStretch()
        self.summary = QLabel()
        filters.addWidget(self.summary)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(QSize(28, 28))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.load_button.clicked.connect(self.load_from_api)
        self.demo_button.clicked.connect(self.load_demo)
        for box in (self.champion_filter, self.role_filter, self.period_filter, self.result_filter):
            box.currentIndexChanged.connect(self.apply_filters)
        self.table.cellDoubleClicked.connect(self._open_row)
        self.session.matches_changed.connect(self._on_matches_changed)

        account = ctx.matches.repository.get_account()
        if account and ctx.matches.can_use_api:
            self.riot_id.setText(account.riot_id)
            self.platform.setCurrentIndex(self.platform.findData(account.platform))
            self.session.set_matches(account, ctx.matches.stored_matches(account.puuid), demo=False)
            self.status.setText(f"Partidas guardadas de {escape(account.riot_id)}. Pulsa «Cargar partidas» para buscar nuevas.")
        else:
            self.load_demo()

    # --- Carga -------------------------------------------------------------

    def load_demo(self) -> None:
        account, matches = self.ctx.matches.demo_matches()
        self.session.set_matches(account, matches, demo=True)
        self.status.setText(
            f"Demostración: {len(matches)} partidas ficticias de «{escape(account.riot_id)}». No son datos reales."
        )

    def load_from_api(self) -> None:
        text = self.riot_id.text().strip()
        if "#" not in text:
            self.status.setText("Escribe tu Riot ID completo con la etiqueta, por ejemplo: MiNombre#LAN.")
            return
        game_name, tag_line = (part.strip() for part in text.rsplit("#", 1))
        if not game_name or not tag_line:
            self.status.setText("El Riot ID debe tener nombre y etiqueta.")
            return
        platform = Platform(self.platform.currentData())
        count = self.count.value()
        self.load_button.setEnabled(False)
        self.status.setText("Consultando la Riot API…")

        def work():
            account = self.ctx.matches.link_account(platform, game_name, tag_line)
            matches, new = self.ctx.matches.fetch_recent(account, count)
            return account, matches, new

        run_task(work, on_done=self._on_loaded, on_error=self._on_load_failed)

    def _on_loaded(self, result) -> None:
        account, matches, new = result
        self.load_button.setEnabled(True)
        self.session.set_matches(account, matches, demo=False)
        self.status.setText(
            f"{escape(account.riot_id)}: {new} partidas nuevas descargadas, {len(matches)} guardadas en total."
        )

    def _on_load_failed(self, error: str) -> None:
        self.load_button.setEnabled(True)
        self.status.setText(f"No se pudieron cargar las partidas: {escape(error)}")

    # --- Tabla y filtros -----------------------------------------------------

    def _names(self) -> dict[str, str]:
        return {c.id: c.name for c in self.ctx.catalog.champions}

    def _on_matches_changed(self) -> None:
        names = self._names()
        self.champion_filter.blockSignals(True)
        self.champion_filter.clear()
        self.champion_filter.addItem("Todos los campeones", None)
        for cid in sorted({m.champion_id for m in self.session.matches}, key=lambda c: names.get(c, c)):
            self.champion_filter.addItem(names.get(cid, cid), cid)
        self.champion_filter.blockSignals(False)
        self.apply_filters()

    def apply_filters(self) -> None:
        match_filter = MatchFilter(
            champion_id=self.champion_filter.currentData(),
            role=combo_role(self.role_filter),
            days=self.period_filter.currentData(),
            win=self.result_filter.currentData(),
        )
        # Las partidas de demostración tienen fechas fijas: se filtran respecto a la más reciente.
        now = self.session.matches[0].played_at if self.session.matches_are_demo and self.session.matches else None
        filtered = match_filter.apply(self.session.matches, now)
        self._fill_table(filtered)
        decided = [m for m in filtered if m.win is not None]
        wins = sum(m.win for m in decided)
        self.summary.setText(f"{len(filtered)} partidas · {wins} victorias" if filtered else "Sin partidas")
        self.session.set_filtered(filtered)

    def _fill_table(self, matches: list[MatchSummary]) -> None:
        names = self._names()
        data = self.ctx.game_data
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(matches))
        for row, m in enumerate(matches):
            result = "Victoria" if m.win else ("Derrota" if m.win is not None else "—")
            if is_probable_remake(m):
                result += " (posible remake)"
            minutes = f"{m.duration_s // 60}:{m.duration_s % 60:02d}" if m.duration_s else "—"
            ratio = kda(m)
            cspm = cs_per_min(m)
            kp = kill_participation(m)
            champ = QTableWidgetItem(QIcon(self.portraits.get(m.champion_id, 28)), names.get(m.champion_id, m.champion_id))
            cells = [
                NumericItem(m.played_at.astimezone().strftime("%d/%m/%Y %H:%M") if m.played_at else "—",
                            m.played_at.timestamp() if m.played_at else None),
                QTableWidgetItem(result),
                champ,
                QTableWidgetItem(m.role.label if m.role else "—"),
                NumericItem(minutes, m.duration_s),
                QTableWidgetItem(f"{fmt(m.kills)} / {fmt(m.deaths)} / {fmt(m.assists)}"),
                NumericItem(fmt(ratio, "{:.2f}"), ratio),
                NumericItem(f"{fmt(m.cs)} ({fmt(cspm, '{:.1f}')})", cspm),
                NumericItem(fmt(m.gold, "{:,}").replace(",", "."), m.gold),
                NumericItem(fmt(m.vision_score), m.vision_score),
                NumericItem(fmt(m.damage_to_champions, "{:,}").replace(",", "."), m.damage_to_champions),
                NumericItem(fmt(m.damage_taken, "{:,}").replace(",", "."), m.damage_taken),
                NumericItem(fmt(kp, "{:.0%}"), kp),
                QTableWidgetItem(),
            ]
            cells[0].setData(Qt.ItemDataRole.UserRole + 1, m.match_id)
            items = cells[-1]
            items.setIcon(QIcon(self._items_strip(m.items)))
            items.setToolTip("\n".join(data.item_name(i) for i in m.items) if data else
                             "Descarga los datos de Data Dragon para ver los nombres.")
            for col, cell in enumerate(cells):
                self.table.setItem(row, col, cell)
        self.table.setIconSize(QSize(ITEM_ICON * 7 + 12, 28))
        self.table.setSortingEnabled(True)

    def _items_strip(self, items: list[int]) -> QPixmap:
        strip = QPixmap(ITEM_ICON * 7 + 12, ITEM_ICON)
        strip.fill(Qt.GlobalColor.transparent)
        painter = QPainter(strip)
        for i, item_id in enumerate(items[:7]):
            painter.drawPixmap(i * (ITEM_ICON + 2), 0, self.portraits.item(item_id, ITEM_ICON))
        painter.end()
        return strip

    def _open_row(self, row: int, _column: int) -> None:
        match_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1)
        self.session.match_selected.emit(match_id)
        self.open_match.emit(match_id)

    def on_catalog_changed(self) -> None:
        self._on_matches_changed()
