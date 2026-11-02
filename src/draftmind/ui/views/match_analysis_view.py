"""Análisis postpartida: detalle de una partida, medias, tendencias y observaciones.

Trabaja con las partidas filtradas en «Historial». Solo usa estadísticas
finales de cada partida: no hay datos de movimientos ni decisiones, así que
no se intenta reconstruir lo que pasó.
"""

from html import escape

import matplotlib

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from draftmind.analysis.lane_analyzer import lane_trend  # noqa: E402
from draftmind.ui.components.visuals import badge_label  # noqa: E402
from draftmind.ui.workers import run_task  # noqa: E402

from draftmind.analysis.postgame_analyzer import (  # noqa: E402
    averages,
    cs_per_min,
    is_probable_remake,
    kda,
    kill_participation,
    observations,
)
from draftmind.app.bootstrap import AppContext  # noqa: E402
from draftmind.domain.models import MatchSummary  # noqa: E402
from draftmind.ui import theme  # noqa: E402
from draftmind.ui.portraits import PortraitProvider  # noqa: E402
from draftmind.ui.session import AppSession  # noqa: E402
from draftmind.ui.widgets import card, notice_label, section_label, subtitle_label, title_label  # noqa: E402

METRICS = [
    ("CS por minuto", cs_per_min),
    ("KDA", kda),
    ("Visión por minuto", lambda m: m.vision_score / (m.duration_s / 60) if m.vision_score is not None and m.duration_s else None),
]


class MatchAnalysisView(QWidget):
    def __init__(self, ctx: AppContext, session: AppSession, portraits: PortraitProvider,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.portraits = portraits
        self.selected: MatchSummary | None = None

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title_label("Análisis postpartida"))
        layout.addWidget(subtitle_label(
            "Usa las partidas filtradas en «Historial». Se basa en estadísticas finales: no incluye "
            "movimientos ni decisiones segundo a segundo, así que no reconstruye lo que pasó."
        ))
        self.demo_notice = notice_label("Estás viendo partidas FICTICIAS de demostración.")
        layout.addWidget(self.demo_notice)

        layout.addWidget(section_label("Partida seleccionada"))
        detail, detail_layout = card()
        self.detail_portrait = QLabel()
        self.detail_text = QLabel()
        self.detail_text.setWordWrap(True)
        self.detail_text.setTextFormat(Qt.TextFormat.RichText)
        self.detail_items = QHBoxLayout()
        self.detail_items.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(self.detail_portrait, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(self.detail_text, 1)
        detail_layout.addLayout(top)
        detail_layout.addLayout(self.detail_items)
        layout.addWidget(detail)

        layout.addWidget(section_label("Fase de líneas"))
        lane_card, lane_layout = card()
        lane_info = QLabel(
            "Oro, CS y experiencia a los 5, 10 y 15 minutos frente a tu rival directo, primera participación en "
            "un asesinato y objetivos tempranos. Usa el timeline oficial (una foto por minuto): no reconstruye "
            "rutas ni decisiones. Cada partida nueva es una petición a la Riot API."
        )
        lane_info.setWordWrap(True)
        lane_info.setStyleSheet(f"color: {theme.MUTED};")
        self.lane_button = QPushButton("Analizar esta partida")
        self.lane_button.setObjectName("primary")
        self.trend_button = QPushButton("Tendencia de las últimas 10 partidas")
        lane_buttons = QHBoxLayout()
        lane_buttons.addWidget(self.lane_button)
        lane_buttons.addWidget(self.trend_button)
        lane_buttons.addStretch()
        self.lane_result = QLabel()
        self.lane_result.setWordWrap(True)
        self.lane_result.setTextFormat(Qt.TextFormat.RichText)
        lane_layout.addWidget(lane_info)
        lane_layout.addLayout(lane_buttons)
        lane_layout.addWidget(self.lane_result)
        layout.addWidget(lane_card)
        self.lane_button.clicked.connect(self.analyze_lane)
        self.trend_button.clicked.connect(self.analyze_trend)

        layout.addWidget(section_label("Medias de la selección"))
        self.stat_labels: dict[str, QLabel] = {}
        stats = QGridLayout()
        stats.setSpacing(10)
        for col, (key, label) in enumerate((("kda", "KDA"), ("cs_per_min", "CS/min"),
                                            ("kill_participation", "Part. asesinatos"),
                                            ("vision", "Visión"), ("deaths", "Muertes"))):
            box, box_layout = card()
            value = QLabel("—")
            value.setStyleSheet("font-size: 17pt; font-weight: 700;")
            caption = QLabel(label)
            caption.setStyleSheet(f"color: {theme.MUTED};")
            box_layout.addWidget(value)
            box_layout.addWidget(caption)
            self.stat_labels[key] = value
            stats.addWidget(box, 0, col)
        layout.addLayout(stats)

        layout.addWidget(section_label("Evolución (orden cronológico)"))
        self.figure = Figure(figsize=(9, 3.2), facecolor=theme.SURFACE)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(260)
        layout.addWidget(self.canvas)

        layout.addWidget(section_label("Observaciones"))
        self.observations = QLabel()
        self.observations.setWordWrap(True)
        self.observations.setTextFormat(Qt.TextFormat.RichText)
        obs_box, obs_layout = card()
        obs_layout.addWidget(self.observations)
        layout.addWidget(obs_box)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        session.filter_changed.connect(self.refresh)
        session.matches_changed.connect(self.refresh)
        session.match_selected.connect(self.select_match)
        self.refresh()

    def select_match(self, match_id: str) -> None:
        self.selected = self.session.match(match_id)
        self._render_detail()

    def refresh(self) -> None:
        matches = self.session.filtered
        self.demo_notice.setVisible(self.session.matches_are_demo)
        if self.selected is None or self.selected not in self.session.matches:
            self.selected = matches[0] if matches else None
        self._render_detail()

        avg = averages(matches)
        formats = {"kda": "{:.2f}", "cs_per_min": "{:.1f}", "kill_participation": "{:.0%}",
                   "vision": "{:.0f}", "deaths": "{:.1f}"}
        for key, label in self.stat_labels.items():
            value = avg[key]
            label.setText("—" if value is None else formats[key].format(value))
        self._plot(matches)
        lines = []
        for o in observations(matches):
            sample = f" <span style='color:{theme.MUTED}'>(n = {o.sample_size})</span>" if o.sample_size else ""
            lines.append(f"<p><b>[{o.kind.label}]</b> {escape(o.text)}{sample}</p>")
        self.observations.setText("".join(lines))

    def _render_detail(self) -> None:
        while self.detail_items.count():
            widget = self.detail_items.takeAt(0).widget()
            if widget:
                widget.setParent(None)
        m = self.selected
        if m is None:
            self.detail_portrait.clear()
            self.detail_text.setText("No hay partidas con los filtros actuales.")
            return
        names = {c.id: c.name for c in self.ctx.catalog.champions}
        data = self.ctx.game_data
        self.detail_portrait.setPixmap(self.portraits.get(m.champion_id, 64))
        result = "Victoria" if m.win else ("Derrota" if m.win is not None else "Resultado desconocido")
        ratio, cspm, kp = kda(m), cs_per_min(m), kill_participation(m)
        keystone = data.rune(m.keystone_id).name if data and m.keystone_id and data.rune(m.keystone_id) else "—"
        spells = ", ".join(s.name for k in m.summoner_spells if data and (s := data.spell(k))) or "—"
        opponent = names.get(m.lane_opponent, m.lane_opponent) if m.lane_opponent else "desconocido"
        remake = " · <b>Posible remake</b> (no cuenta en las medias)" if is_probable_remake(m) else ""
        when = m.played_at.astimezone().strftime("%d/%m/%Y %H:%M") if m.played_at else "fecha desconocida"
        self.detail_text.setText(
            f"<span style='font-size:13pt'><b>{escape(names.get(m.champion_id, m.champion_id))}</b> · {result}</span>{remake}<br>"
            f"{when} · {m.role.label if m.role else 'posición desconocida'} · parche {m.patch or '—'} · "
            f"{(m.duration_s or 0) // 60} min<br>"
            f"K/D/A {m.kills}/{m.deaths}/{m.assists} (KDA {'—' if ratio is None else f'{ratio:.2f}'}) · "
            f"CS {m.cs if m.cs is not None else '—'} ({'—' if cspm is None else f'{cspm:.1f}'}/min) · "
            f"Part. asesinatos {'—' if kp is None else f'{kp:.0%}'} · Visión {m.vision_score if m.vision_score is not None else '—'}<br>"
            f"Rival directo: {escape(opponent)} · Runa clave: {escape(keystone)} · Hechizos: {escape(spells)}"
            + (f"<br>Puntuación de rendimiento: <b>{m.performance_score:.1f}</b>/10 · puesto "
               f"{m.performance_rank} de 10 {badge_label(m.badge)}" if m.performance_score is not None else "")
        )
        self.lane_result.setText("")
        self.lane_button.setEnabled(not m.is_demo)
        for item_id in m.items:
            icon = QLabel()
            icon.setPixmap(self.portraits.item(item_id, 32))
            icon.setToolTip(data.item_name(item_id) if data else f"Objeto #{item_id}")
            self.detail_items.addWidget(icon)
        self.detail_items.addStretch()

    # --- Fase de líneas -----------------------------------------------------------

    def analyze_lane(self) -> None:
        match = self.selected
        if match is None:
            return
        if match.is_demo or not self.ctx.matches.can_use_api:
            self.lane_result.setText("Disponible con tus partidas reales descargadas y tu API key.")
            return
        self.lane_button.setEnabled(False)
        self.lane_result.setText("Consultando el timeline…")

        def done(analysis) -> None:
            self.lane_button.setEnabled(True)
            if analysis is None:
                self.lane_result.setText("No se pudo analizar esta partida (faltan datos del timeline).")
                return
            self.lane_result.setText(self._lane_html(analysis))

        def failed(error: str) -> None:
            self.lane_button.setEnabled(True)
            self.lane_result.setText(f"Error al consultar el timeline: {escape(error)}")

        run_task(lambda: self.ctx.matches.lane_analysis(match), on_done=done, on_error=failed)

    def analyze_trend(self) -> None:
        matches = [m for m in self.session.filtered if not m.is_demo]
        if not matches or not self.ctx.matches.can_use_api:
            self.lane_result.setText("Disponible con tus partidas reales descargadas y tu API key.")
            return
        self.trend_button.setEnabled(False)
        self.lane_result.setText("Consultando hasta 10 timelines (los ya descargados no se repiten)…")

        def done(analyses) -> None:
            self.trend_button.setEnabled(True)
            parts = []
            for minute in (10, 15):
                trend = lane_trend(analyses, minute)
                if trend:
                    parts.append(f"<p><b>[{trend.kind.label}]</b> {escape(trend.text)}</p>")
            first = [a.first_takedown_minute for a in analyses if a.first_takedown_minute is not None]
            if len(first) >= 3:
                parts.append(f"<p><b>[Estadística observada]</b> Tu primera participación en un asesinato llega, "
                             f"de media, en el minuto {sum(first) / len(first):.1f} ({len(first)} partidas).</p>")
            deaths = [a.deaths_before_15 for a in analyses]
            if len(deaths) >= 3:
                parts.append(f"<p><b>[Estadística observada]</b> Mueres {sum(deaths) / len(deaths):.1f} veces de "
                             f"media antes del minuto 15 ({len(deaths)} partidas).</p>")
            self.lane_result.setText("".join(parts) or "Hacen falta al menos 3 partidas con datos completos.")

        def failed(error: str) -> None:
            self.trend_button.setEnabled(True)
            self.lane_result.setText(f"Error al consultar los timelines: {escape(error)}")

        run_task(lambda: self.ctx.matches.lane_analyses(matches, limit=10), on_done=done, on_error=failed)

    @staticmethod
    def _lane_html(a) -> str:
        def fmt(value, signed=False):
            if value is None:
                return "—"
            return f"{value:+,}".replace(",", ".") if signed else f"{value:,}".replace(",", ".")

        rows = "".join(
            f"<tr><td><b>Min {s.minute}</b></td>"
            f"<td>{fmt(s.gold)} / {fmt(s.opponent_gold)}</td><td><b>{fmt(s.gold_diff, True)}</b></td>"
            f"<td>{s.cs} / {fmt(s.opponent_cs)}</td><td><b>{fmt(s.cs_diff, True)}</b></td>"
            f"<td>{fmt(s.xp_diff, True)}</td></tr>"
            for s in a.snapshots
        )
        table = ("<table cellspacing='0' cellpadding='6'><tr style='color:#8a94a3'><th align='left'></th>"
                 "<th align='left'>Oro (tú / rival)</th><th align='left'>Dif.</th><th align='left'>CS (tú / rival)</th>"
                 f"<th align='left'>Dif.</th><th align='left'>Dif. XP</th></tr>{rows}</table>")
        objectives = a.objectives_before_15
        objective_text = " · ".join(
            f"{side.capitalize()}: " + (", ".join(f"{n} {name}" for name, n in values.items()) or "ninguno")
            for side, values in objectives.items()
        )
        observations = "".join(f"<p><b>[{o.kind.label}]</b> {escape(o.text)}</p>" for o in a.observations)
        return f"{table}<p>Objetivos antes del minuto 15 — {escape(objective_text)}</p>{observations}"

    def _plot(self, matches: list[MatchSummary]) -> None:
        self.figure.clear()
        ordered = sorted((m for m in matches if m.played_at and not is_probable_remake(m)),
                         key=lambda m: m.played_at)
        if len(ordered) < 2:
            ax = self.figure.add_subplot(111)
            ax.set_axis_off()
            ax.text(0.5, 0.5, "Hacen falta al menos 2 partidas para ver la evolución.",
                    color=theme.MUTED, ha="center", va="center")
            self.canvas.draw_idle()
            return
        x = list(range(1, len(ordered) + 1))
        for index, (label, metric) in enumerate(METRICS, start=1):
            ax = self.figure.add_subplot(1, len(METRICS), index)
            ax.set_facecolor(theme.SURFACE)
            values = [metric(m) for m in ordered]
            points = [(xi, v) for xi, v in zip(x, values) if v is not None]
            if points:
                ax.plot([p[0] for p in points], [p[1] for p in points], color=theme.ACCENT, linewidth=1.5)
                # Forma distinta para victoria (círculo) y derrota (aspa): no depende del color.
                for xi, v, m in ((xi, v, m) for xi, v, m in zip(x, values, ordered) if v is not None):
                    ax.plot(xi, v, marker="o" if m.win else "x", color=theme.TEXT if m.win else theme.ENEMY,
                            markersize=5, linestyle="none")
            ax.set_title(label, color=theme.TEXT, fontsize=9)
            ax.tick_params(colors=theme.MUTED, labelsize=7)
            for spine in ax.spines.values():
                spine.set_color(theme.BORDER)
            ax.grid(color=theme.BORDER, linewidth=0.5)
        self.figure.text(0.99, 0.01, "○ victoria   × derrota", color=theme.MUTED, fontsize=7, ha="right")
        self.figure.tight_layout(rect=(0, 0.04, 1, 1))
        self.canvas.draw_idle()

    def on_catalog_changed(self) -> None:
        self.refresh()
