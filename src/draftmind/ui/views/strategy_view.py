"""Estrategia y composición a partir del draft montado en «Draft»."""

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from draftmind.analysis.strategy_analyzer import TeamStrategy, analyze_strategy
from draftmind.app.bootstrap import AppContext
from draftmind.ui import theme
from draftmind.ui.session import AppSession
from draftmind.ui.widgets import card, notice_label, section_label, subtitle_label, title_label


def _list(items: list[str]) -> str:
    return "".join(f"<div>• {escape(i)}</div>" for i in items) or f"<div style='color:{theme.MUTED}'>Ninguno.</div>"


class StrategyView(QWidget):
    open_draft = Signal()

    def __init__(self, ctx: AppContext, session: AppSession, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.session = session

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(title_label("Estrategia"))
        titles.addWidget(subtitle_label(
            "Condiciones de victoria, ventanas de poder y riesgos del draft actual. Los hechos salen de los "
            "campeones elegidos; todo lo demás son hipótesis para reflexionar, no órdenes."
        ))
        header.addLayout(titles, 1)
        go = QPushButton("Editar el draft")
        go.clicked.connect(self.open_draft.emit)
        header.addWidget(go)
        layout.addLayout(header)
        self.notice = notice_label("Añade al menos 3 campeones con perfil en cada equipo en «Draft» para un análisis más completo.")
        layout.addWidget(self.notice)

        teams = QHBoxLayout()
        self.ally_label, self.enemy_label = QLabel(), QLabel()
        for title, label, object_name in (("TU EQUIPO", self.ally_label, "teamAlly"),
                                           ("EQUIPO ENEMIGO", self.enemy_label, "teamEnemy")):
            box, box_layout = card()
            heading = QLabel(title)
            heading.setObjectName(object_name)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            box_layout.addWidget(heading)
            box_layout.addWidget(label)
            box_layout.addStretch()
            teams.addWidget(box)
        layout.addLayout(teams)

        layout.addWidget(section_label("Comparación"))
        self.comparison = QLabel()
        self.comparison.setWordWrap(True)
        comp_box, comp_layout = card()
        comp_layout.addWidget(self.comparison)
        layout.addWidget(comp_box)

        layout.addWidget(section_label("Preguntas para plantearte durante la partida"))
        self.questions = QLabel()
        self.questions.setWordWrap(True)
        self.questions.setTextFormat(Qt.TextFormat.RichText)
        q_box, q_layout = card()
        q_layout.addWidget(self.questions)
        layout.addWidget(q_box)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        session.draft_changed.connect(self.refresh)
        self.refresh()

    @staticmethod
    def _team_html(strategy: TeamStrategy, names: list[str]) -> str:
        return (
            f"<p style='color:{theme.MUTED}'>{escape(', '.join(names)) or 'Sin campeones'}</p>"
            f"<p><b>Hechos del draft</b></p>{_list(strategy.facts)}"
            f"<p><b>Condiciones de victoria</b> <i>[Inferencia estratégica]</i></p>{_list(strategy.win_conditions)}"
            f"<p><b>Riesgos</b> <i>[Inferencia estratégica]</i></p>{_list(strategy.risks)}"
        )

    def refresh(self) -> None:
        allies, enemies = self.ctx.analyzer.compositions(self.session.draft)
        report = analyze_strategy(allies, enemies)
        names = {c.id: c.name for c in self.ctx.catalog.champions}
        self.notice.setVisible(not report.enough_data)
        self.ally_label.setText(self._team_html(report.ally, [names.get(i, i) for i in allies.champion_ids]))
        self.enemy_label.setText(self._team_html(report.enemy, [names.get(i, i) for i in enemies.champion_ids]))
        self.comparison.setText(f"{report.power_window}\n\n{report.objectives}")
        self.questions.setText("".join(f"<div>• {escape(q)}</div>" for q in report.questions))

    def on_catalog_changed(self) -> None:
        self.refresh()
