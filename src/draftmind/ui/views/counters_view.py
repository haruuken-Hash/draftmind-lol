"""Counters y enfrentamientos: tu campeón contra un rival directo."""

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from draftmind.analysis.matchup_analyzer import analyze_matchup, patch_of
from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import Role
from draftmind.ui import theme
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.session import AppSession
from draftmind.ui.widgets import card, combo_role, section_label, subtitle_label, title_label


class CountersView(QWidget):
    def __init__(self, ctx: AppContext, session: AppSession, portraits: PortraitProvider,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.portraits = portraits

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title_label("Counters y enfrentamientos"))
        layout.addWidget(subtitle_label(
            "Compara tu campeón con el rival de tu línea. Se separa lo observado en datos de lo que es "
            "una inferencia. Ningún campeón es un «counter» absoluto: se describen condiciones."
        ))

        self.role = QComboBox()
        self.role.addItem("Cualquier posición", None)
        for r in Role:
            self.role.addItem(r.label, r)
        self.mine = QComboBox()
        self.rival = QComboBox()
        swap = QPushButton("Intercambiar")
        selectors = QHBoxLayout()
        for label, widget in (("Posición:", self.role), ("Tu campeón:", self.mine), ("Rival:", self.rival)):
            selectors.addWidget(QLabel(label))
            selectors.addWidget(widget, 1)
        selectors.addWidget(swap)
        layout.addLayout(selectors)

        header, header_layout = card()
        self.vs = QLabel()
        self.vs.setTextFormat(Qt.TextFormat.RichText)
        self.mine_portrait, self.rival_portrait = QLabel(), QLabel()
        vs_row = QHBoxLayout()
        vs_row.addWidget(self.mine_portrait)
        vs_row.addWidget(self.vs, 1)
        vs_row.addWidget(self.rival_portrait)
        header_layout.addLayout(vs_row)
        layout.addWidget(header)

        layout.addWidget(section_label("Estadísticas observadas"))
        self.evidence = QLabel()
        self.evidence.setWordWrap(True)
        self.evidence.setTextFormat(Qt.TextFormat.RichText)
        ev_box, ev_layout = card()
        ev_layout.addWidget(self.evidence)
        layout.addWidget(ev_box)

        layout.addWidget(section_label("Condiciones del enfrentamiento"))
        self.insights = QLabel()
        self.insights.setWordWrap(True)
        self.insights.setTextFormat(Qt.TextFormat.RichText)
        in_box, in_layout = card()
        in_layout.addWidget(self.insights)
        layout.addWidget(in_box)

        self.history_title = section_label("")
        layout.addWidget(self.history_title)
        self.history = QTableWidget(0, 5)
        self.history.setHorizontalHeaderLabels(["Rival", "Partidas", "Victorias", "Win rate", "Fuente"])
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.verticalHeader().setVisible(False)
        self.history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.history.horizontalHeader().setStretchLastSection(True)
        self.history.setMinimumHeight(200)
        self.history.cellDoubleClicked.connect(self._pick_rival_from_table)
        layout.addWidget(self.history)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        for box in (self.role, self.mine, self.rival):
            box.currentIndexChanged.connect(self.refresh)
        swap.clicked.connect(self._swap)
        session.matches_changed.connect(self.refresh)
        self.on_catalog_changed()

    def _fill_champions(self) -> None:
        current = (self.mine.currentData(), self.rival.currentData())
        for box in (self.mine, self.rival):
            box.blockSignals(True)
            box.clear()
            for c in self.ctx.catalog.champions:
                box.addItem(QIcon(self.portraits.get(c.id, 20)), c.name, c.id)
            box.blockSignals(False)
        defaults = current if all(current) else ("Garen", "Darius")
        for box, cid in zip((self.mine, self.rival), defaults):
            index = box.findData(cid)
            box.setCurrentIndex(index if index >= 0 else 0)

    def _swap(self) -> None:
        mine, rival = self.mine.currentData(), self.rival.currentData()
        self.mine.blockSignals(True)
        self.mine.setCurrentIndex(self.mine.findData(rival))
        self.mine.blockSignals(False)
        self.rival.setCurrentIndex(self.rival.findData(mine))

    def _pick_rival_from_table(self, row: int, _col: int) -> None:
        rival_id = self.history.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.rival.setCurrentIndex(self.rival.findData(rival_id))

    def refresh(self) -> None:
        mine, rival, role = self.mine.currentData(), self.rival.currentData(), combo_role(self.role)
        if not mine or not rival:
            return
        names = {c.id: c.name for c in self.ctx.catalog.champions}
        profiles = {c.id: c for c in self.ctx.analyzer.champions}
        result = analyze_matchup(mine, rival, role, self.ctx.stats.providers, profiles,
                                 self.ctx.analyzer.profile, patch_of(self.ctx.catalog.version))

        self.mine_portrait.setPixmap(self.portraits.get(mine, 64))
        self.rival_portrait.setPixmap(self.portraits.get(rival, 64))
        reasons = " ".join(result.confidence.reasons)
        warnings = "".join(f"<br><b>Advertencia:</b> {escape(w)}" for w in result.warnings)
        self.vs.setText(
            f"<div style='text-align:center'><span style='font-size:15pt'><b>{escape(names.get(mine, mine))}</b>"
            f"  contra  <b>{escape(names.get(rival, rival))}</b></span><br>"
            f"Confianza: <b>{result.confidence.level.label}</b><br>"
            f"<span style='color:{theme.MUTED}'>{escape(reasons)}</span>{warnings}</div>"
        )

        if result.evidence:
            self.evidence.setText("".join(
                f"<p><b>[Estadística observada · confianza {e.confidence.level.label.lower()}]</b> {escape(e.text)}</p>"
                for e in result.evidence
            ))
        else:
            sources = ", ".join(p.name for p in self.ctx.stats.providers) or "ninguna"
            self.evidence.setText(
                f"<i>Evidencia insuficiente: no hay estadísticas de este enfrentamiento en las fuentes "
                f"conectadas ({escape(sources)}).</i> Puedes cargar tus partidas en «Historial» o importar "
                "estadísticas en «Fuentes y configuración»."
            )
        self.insights.setText("".join(
            f"<p><b>[{i.kind.label}]</b> {escape(i.text)}</p>" for i in result.insights
        ))

        rows = [s for p in self.ctx.stats.providers for s in p.opponents(mine, role)]
        self.history_title.setText(f"Enfrentamientos observados de {names.get(mine, mine)} (doble clic para analizar)")
        self.history.setRowCount(len(rows))
        for r, stat in enumerate(rows):
            wr = stat.observed_win_rate
            rival_item = QTableWidgetItem(QIcon(self.portraits.get(stat.opponent_id, 22)),
                                          names.get(stat.opponent_id, stat.opponent_id))
            rival_item.setData(Qt.ItemDataRole.UserRole, stat.opponent_id)
            for c, item in enumerate((
                rival_item, QTableWidgetItem(str(stat.games)),
                QTableWidgetItem("—" if stat.wins is None else str(stat.wins)),
                QTableWidgetItem("—" if wr is None else f"{wr:.0%}" + (" (muestra muy pequeña)" if stat.games < 10 else "")),
                QTableWidgetItem(stat.source.name),
            )):
                self.history.setItem(r, c, item)

    def on_catalog_changed(self) -> None:
        self._fill_champions()
        self.refresh()
