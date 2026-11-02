"""Tablero de draft interactivo con análisis en vivo.

Flujo: haz clic en una casilla (o deja que la aplicación elija la siguiente
vacía) y después en un campeón de la cuadrícula. Cada cambio recalcula las
recomendaciones al instante. Clic derecho o Supr vacía una casilla.

El tablero nunca actúa sobre el cliente del juego. Con el draft en vivo
activado (opcional, en «Fuentes y configuración»), además LEE la selección
de campeones del cliente y la refleja aquí; durante la partida se detiene.
"""

from html import escape

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from draftmind.analysis.ban_analyzer import suggest_bans
from draftmind.analysis.build_analyzer import build_advice
from draftmind.analysis.composition_analyzer import analyze_team
from draftmind.analysis.champion_stats import comfort_pool
from draftmind.analysis.lane_matchup import analyze_matchup, assign_enemy_roles, gank_danger, gank_options
from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import EvidenceKind, Role
from draftmind.domain.models import CandidateAnalysis, DraftPick, DraftState, TeamProfile
from draftmind.integrations.champ_select import LiveDraft, LiveSlot
from draftmind.services.live_draft_service import LiveDraftService, LiveState, LiveStatus
from draftmind.ui import theme
from draftmind.ui.components.champion_grid import ChampionGrid
from draftmind.ui.components.champion_slot import ChampionSlot
from draftmind.ui.components.recommendation_card import RecommendationCard
from draftmind.ui.build_report import build_advice_html
from draftmind.ui.draft_report import render_report
from draftmind.ui.matchup_report import danger_html, ganks_html, matchup_html
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.session import AppSession
from draftmind.ui.widgets import (
    card,
    combo_role,
    notice_label,
    section_label,
    subtitle_label,
    title_label,
)
from draftmind.ui.workers import run_task

CARD_COLUMNS = 2
BAN_COLUMNS = 3
SUGGESTIONS = 6
LIVE_POLL_MS = 2000  # Cada 2 s: como mucho 2 peticiones locales al cliente.


class DraftView(QWidget):
    champ_select_started = Signal()

    def __init__(self, ctx: AppContext, session: AppSession, portraits: PortraitProvider,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.portraits = portraits
        self.active_slot: ChampionSlot | None = None
        self._analyses: list[CandidateAnalysis] = []
        self.bans: list[str] = []
        # Draft en vivo.
        self._live_service: LiveDraftService | None = None
        self._live_busy = False
        self._last_live: LiveDraft | None = None
        self._last_live_state: LiveState | None = None
        self._enemy_roles: dict[int, Role | None] = {}  # Roles enemigos que indica el usuario.
        # Enfrentamiento: consejos oficiales y oro al minuto 10, guardados para no repetir trabajo.
        self._enemy_tips: dict[str, list[str]] = {}
        self._tips_loading: set[str] = set()
        self._gold_at_10: dict[str, int | None] = {}
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(LIVE_POLL_MS)
        self._live_timer.timeout.connect(self._poll_live)

        # --- Cabecera ---
        self.my_role = QComboBox()
        self.my_role.addItem("Sin indicar", None)
        for role in Role:
            self.my_role.addItem(role.label, role)
        if ctx.analyzer.profile.main_roles:
            self.my_role.setCurrentIndex(self.my_role.findData(ctx.analyzer.profile.main_roles[0]))
        report_button = QPushButton("Informe completo")
        clear_button = QPushButton("Limpiar tablero")

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(title_label("Draft"))
        titles.addWidget(subtitle_label(
            "Clic en una casilla y luego en un campeón. Clic derecho o Supr vacía la casilla. "
            "Esc cancela la selección. Ctrl+F busca."
        ))
        header.addLayout(titles, 1)
        header.addWidget(QLabel("Tu posición:"))
        header.addWidget(self.my_role)
        header.addWidget(report_button)
        header.addWidget(clear_button)

        # --- Equipos ---
        self.ally_slots = [ChampionSlot(portraits, role, editable_role=False) for role in Role]
        self.enemy_slots = [ChampionSlot(portraits, role, editable_role=True) for role in Role]
        allies_col = self._team_column("TU EQUIPO", "teamAlly", self.ally_slots)
        enemies_col = self._team_column("EQUIPO ENEMIGO", "teamEnemy", self.enemy_slots)

        # --- Centro: cuadrícula + análisis ---
        self.grid = ChampionGrid(ctx, portraits)
        self.analysis_heading = section_label("")
        self.analysis_notes = QLabel()
        self.analysis_notes.setWordWrap(True)
        self.analysis_notes.setStyleSheet("color: #8b929c;")
        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(10)
        self.ally_summary = QLabel()
        self.enemy_summary = QLabel()
        for label in (self.ally_summary, self.enemy_summary):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
        ally_box, ally_box_layout = card()
        ally_box_layout.addWidget(self.ally_summary)
        enemy_box, enemy_box_layout = card()
        enemy_box_layout.addWidget(self.enemy_summary)
        summaries = QHBoxLayout()
        summaries.addWidget(ally_box)
        summaries.addWidget(enemy_box)

        analysis = QWidget()
        analysis_layout = QVBoxLayout(analysis)
        analysis_layout.setContentsMargins(0, 8, 6, 0)
        analysis_layout.addWidget(section_label("Bloqueos sugeridos"))
        self.ban_note = QLabel()
        self.ban_note.setWordWrap(True)
        self.ban_note.setStyleSheet(f"color: {theme.MUTED};")
        self.ban_row = QGridLayout()  # Cuadrícula: no ensancha el panel aunque haya 5 sugerencias.
        self.ban_row.setSpacing(8)
        analysis_layout.addWidget(self.ban_note)
        analysis_layout.addLayout(self.ban_row)
        analysis_layout.addWidget(self.analysis_heading)
        analysis_layout.addWidget(self.analysis_notes)
        analysis_layout.addLayout(self.cards_layout)
        self.matchup_heading = section_label("Tu enfrentamiento")
        self.matchup_label = QLabel()
        self.matchup_label.setWordWrap(True)
        self.matchup_label.setTextFormat(Qt.TextFormat.RichText)
        matchup_box, matchup_box_layout = card()
        matchup_box_layout.addWidget(self.matchup_label)
        self.gank_heading = section_label("Gankeos")
        self.gank_label = QLabel()
        self.gank_label.setWordWrap(True)
        self.gank_label.setTextFormat(Qt.TextFormat.RichText)
        self.gank_box, gank_box_layout = card()
        gank_box_layout.addWidget(self.gank_label)
        analysis_layout.addWidget(self.matchup_heading)
        analysis_layout.addWidget(matchup_box)
        analysis_layout.addWidget(self.gank_heading)
        analysis_layout.addWidget(self.gank_box)
        self.build_heading = section_label("Build")
        self.build_label = QLabel()
        self.build_label.setWordWrap(True)
        self.build_label.setTextFormat(Qt.TextFormat.RichText)
        build_box, build_box_layout = card()
        build_box_layout.addWidget(self.build_label)
        analysis_layout.addWidget(self.build_heading)
        analysis_layout.addWidget(build_box)
        analysis_layout.addWidget(section_label("Composiciones"))
        analysis_layout.addLayout(summaries)
        analysis_layout.addStretch()
        analysis_scroll = QScrollArea()
        analysis_scroll.setWidgetResizable(True)
        analysis_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        analysis_scroll.setWidget(analysis)

        center = QSplitter(Qt.Orientation.Vertical)
        center.addWidget(self.grid)
        center.addWidget(analysis_scroll)
        center.setSizes([300, 420])

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addLayout(allies_col)
        body.addWidget(center, 1)
        body.addLayout(enemies_col)

        # --- Barra del draft en vivo (solo si está activado) ---
        self.live_bar, live_layout = card()
        live_badge = QLabel("EN VIVO")
        live_badge.setObjectName("badge")
        self.live_status = QLabel()
        self.live_status.setWordWrap(True)
        self.live_toggle = QPushButton("Pausar seguimiento")
        self.live_toggle.setCheckable(True)
        self.live_toggle.setToolTip("Deja de leer el cliente para editar el tablero a mano.")
        live_row = QHBoxLayout()
        live_row.addWidget(live_badge)
        live_row.addWidget(self.live_status, 1)
        live_row.addWidget(self.live_toggle)
        self.bans_row = QHBoxLayout()
        self.bans_row.setSpacing(4)
        live_layout.addLayout(live_row)
        live_layout.addLayout(self.bans_row)
        self.live_bar.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.addLayout(header)
        layout.addWidget(self.live_bar)
        layout.addLayout(body, 1)

        # --- Señales ---
        for slot in self.ally_slots + self.enemy_slots:
            slot.activated.connect(self.activate)
            slot.cleared.connect(self.clear_slot)
            slot.role_changed.connect(self._on_slot_role_changed)
        self.live_toggle.toggled.connect(self._on_live_toggled)
        self.grid.champion_chosen.connect(self.place_champion)
        self.my_role.currentIndexChanged.connect(self._on_my_role_changed)
        clear_button.clicked.connect(self.clear)
        report_button.clicked.connect(self.show_report)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.grid.search.setFocus)
        QShortcut(QKeySequence("Esc"), self, activated=lambda: self.activate(None))

        self._on_my_role_changed()
        self.configure_live()

    @staticmethod
    def _team_column(title: str, object_name: str, slots: list[ChampionSlot]) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(8)
        label = QLabel(title)
        label.setObjectName(object_name)
        column.addWidget(label)
        for slot in slots:
            slot.setFixedWidth(220)
            column.addWidget(slot)
        column.addStretch()
        return column

    # --- Estado del tablero --------------------------------------------------

    def _names(self) -> dict[str, str]:
        return {c.id: c.name for c in self.ctx.catalog.champions}

    def my_slot(self) -> ChampionSlot | None:
        role = combo_role(self.my_role)
        return next((s for s in self.ally_slots if s.role is role), None) if role else None

    def current_draft(self) -> DraftState:
        me = self.my_slot()
        return DraftState(
            my_role=combo_role(self.my_role),
            my_champion_id=me.champion_id if me else None,
            allies=[
                DraftPick(champion_id=s.champion_id, role=s.role)
                for s in self.ally_slots if s.champion_id and s is not me
            ],
            enemies=[
                DraftPick(champion_id=s.champion_id, role=s.role)
                for s in self.enemy_slots if s.champion_id
            ],
            bans=list(self.bans),
        )

    def _taken(self) -> set[str]:
        return {s.champion_id for s in self.ally_slots + self.enemy_slots if s.champion_id} | set(self.bans)

    # --- Acciones ----------------------------------------------------------

    def activate(self, slot: ChampionSlot | None) -> None:
        """Marca la casilla que recibirá el próximo campeón (None = ninguna)."""
        if self.active_slot is not None:
            self.active_slot.set_active(False)
        self.active_slot = slot
        if slot is not None:
            slot.set_active(True)

    def _default_target(self) -> ChampionSlot | None:
        me = self.my_slot()
        if me is not None and me.champion_id is None:
            return me
        return next((s for s in self.ally_slots + self.enemy_slots if s.champion_id is None), None)

    def place_champion(self, champion_id: str) -> None:
        if champion_id in self._taken():
            return
        target = self.active_slot or self._default_target()
        if target is None:
            return
        target.set_champion(champion_id, self._names().get(champion_id, champion_id))
        # Avanza a la siguiente casilla vacía para encadenar selecciones.
        self.activate(None)
        if target is not None:
            order = self.ally_slots + self.enemy_slots
            start = order.index(target)
            following = next((s for s in order[start + 1:] if s.champion_id is None), None)
            if following is not None:
                self.activate(following)
        self._after_change()

    def pick_for_me(self, champion_id: str) -> None:
        me = self.my_slot()
        if me is None or champion_id in self._taken():
            return
        me.set_champion(champion_id, self._names().get(champion_id, champion_id))
        self._after_change()

    def clear_slot(self, slot: ChampionSlot) -> None:
        slot.set_champion(None, None)
        self._after_change()

    def clear(self) -> None:
        self.activate(None)
        for slot in self.ally_slots + self.enemy_slots:
            slot.set_champion(None, None)
            slot.cell_id = None
        self.bans = []
        self._last_live = None
        self._enemy_roles.clear()
        self._render_bans()
        self._after_change()

    def _on_slot_role_changed(self, slot: ChampionSlot) -> None:
        if slot.cell_id is not None and slot in self.enemy_slots:
            self._enemy_roles[slot.cell_id] = slot.role  # Se conserva en las siguientes lecturas.
        self.update_analysis()

    # --- Draft en vivo -------------------------------------------------------

    def configure_live(self) -> None:
        """Activa o desactiva el seguimiento según la configuración guardada."""
        settings = self.ctx.app_settings
        if settings.live_draft_enabled:
            self._live_service = LiveDraftService(settings.league_install_dir, self.ctx.champion_keys)
            self.live_bar.show()
            self.live_status.setText("Buscando el cliente de LoL…")
            if not self.live_toggle.isChecked():
                self._live_timer.start()
                self._poll_live()
        else:
            self._live_service = None
            self._live_timer.stop()
            self.live_bar.hide()

    def _on_live_toggled(self, paused: bool) -> None:
        self.live_toggle.setText("Reanudar seguimiento" if paused else "Pausar seguimiento")
        if paused:
            self._live_timer.stop()
            self.live_status.setText("Seguimiento en pausa: puedes editar el tablero a mano.")
        elif self._live_service is not None:
            self._live_timer.start()
            self._poll_live()

    def _poll_live(self) -> None:
        if self._live_busy or self._live_service is None:
            return
        self._live_busy = True
        run_task(self._live_service.poll, on_done=self.apply_live_status, on_error=self._on_live_error)

    def _on_live_error(self, error: str) -> None:
        self._live_busy = False
        self.live_status.setText(f"Error inesperado al leer el cliente: {escape(error)}")

    def apply_live_status(self, status: LiveStatus) -> None:
        self._live_busy = False
        if self._live_service is None or self.live_toggle.isChecked():
            return  # Desactivado o en pausa mientras llegaba la respuesta.
        entering = status.state is LiveState.CHAMP_SELECT and self._last_live_state is not LiveState.CHAMP_SELECT
        self._last_live_state = status.state
        if entering:
            self.champ_select_started.emit()  # La ventana principal muestra el Draft.
        text = escape(status.message)
        if not status.certificate_verified:
            text += (f" <span style='color:{theme.MUTED}'>(certificado local no verificado con la CA de "
                     "Riot; conexión solo a 127.0.0.1)</span>")
        self.live_status.setText(text)
        if status.state is LiveState.CHAMP_SELECT and status.draft is not None and status.draft != self._last_live:
            self.apply_live_draft(status.draft)

    def apply_live_draft(self, draft: LiveDraft) -> None:
        """Refleja en el tablero lo que muestra el cliente (sin nombres de jugadores)."""
        self._last_live = draft
        names = self._names()
        self.activate(None)
        for slot in self.ally_slots + self.enemy_slots:
            slot.set_champion(None, None)
            slot.cell_id = None

        def put(slot: ChampionSlot, live: LiveSlot) -> None:
            slot.cell_id = live.cell_id
            if live.champion_id:
                slot.set_champion(live.champion_id, names.get(live.champion_id, live.champion_id),
                                  tentative=live.is_intent)

        # Tu posición: la que asigna el cliente; si no hay, la que tengas elegida.
        if draft.me is not None and draft.me.role is not None:
            self.my_role.blockSignals(True)
            self.my_role.setCurrentIndex(self.my_role.findData(draft.me.role))
            self.my_role.blockSignals(False)
        free = list(self.ally_slots)
        me_slot = self.my_slot()
        if draft.me is not None:
            # Sin posición asignada (p. ej. selección a ciegas): no ocupar la de un aliado que sí la tiene.
            claimed = {a.role for a in draft.allies if a.role is not None}
            if draft.me.role is None and (me_slot is None or me_slot.role in claimed):
                me_slot = next((s for s in free if s.role not in claimed), free[0])
            if me_slot is not self.my_slot():
                self.my_role.blockSignals(True)
                self.my_role.setCurrentIndex(self.my_role.findData(me_slot.role))
                self.my_role.blockSignals(False)
            put(me_slot, draft.me)
            free.remove(me_slot)
        pending = []
        for ally in draft.allies:
            slot = next((s for s in free if ally.role is not None and s.role is ally.role), None)
            if slot is None:
                pending.append(ally)
                continue
            put(slot, ally)
            free.remove(slot)
        for ally, slot in zip(pending, free):
            put(slot, ally)

        for slot in self.enemy_slots:
            slot.set_role(None)  # El cliente no muestra los roles enemigos.
        for enemy, slot in zip(draft.enemies, self.enemy_slots):
            put(slot, enemy)
            slot.set_role(self._enemy_roles.get(enemy.cell_id))  # Salvo los que indique el usuario.

        self.bans = list(draft.bans)
        self._render_bans()
        for slot in self.ally_slots:
            slot.set_me(slot is self.my_slot())
        self._after_change()

    def _render_bans(self) -> None:
        while self.bans_row.count():
            widget = self.bans_row.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
        if not self.bans:
            return
        caption = QLabel("Bloqueados:")
        caption.setStyleSheet(f"color: {theme.MUTED};")
        self.bans_row.addWidget(caption)
        names = self._names()
        for champion_id in self.bans:
            icon = QLabel()
            icon.setPixmap(self.portraits.get(champion_id, 26))
            icon.setToolTip(names.get(champion_id, champion_id))
            self.bans_row.addWidget(icon)
        self.bans_row.addStretch()

    def _on_my_role_changed(self) -> None:
        me = self.my_slot()
        for slot in self.ally_slots:
            slot.set_me(slot is me)
        self.update_analysis()

    def _after_change(self) -> None:
        self.grid.set_unavailable(self._taken())
        self.update_analysis()

    # --- Análisis en vivo ----------------------------------------------------

    def update_analysis(self) -> None:
        analyzer = self.ctx.analyzer
        draft = self.current_draft()
        self.session.set_draft(draft)  # «Estrategia» y «Runas y builds» lo leen.
        me = self.my_slot()
        mine = draft.my_champion_id
        names = self._names()

        entries: list[tuple[CandidateAnalysis, str | None, bool]] = []
        notes: list[str] = []
        if mine and analyzer.has_profile(mine):
            self.analysis_heading.setText("Tu elección y alternativas")
            entries.append((analyzer.analyze_candidate(draft, mine), "Tu elección", False))
            alternatives = [a for a in analyzer.suggest_candidates(draft, limit=4) if a.champion.id != mine]
            entries += [(a, "Alternativa", True) for a in alternatives[:3]]
        else:
            role = draft.my_role
            self.analysis_heading.setText(
                f"Sugerencias para {role.label}" if role else "Sugerencias (indica tu posición para afinarlas)"
            )
            if mine:
                notes.append(f"{escape(names.get(mine, mine))} no tiene perfil cualitativo: evidencia insuficiente para analizarlo.")
            suggestions = [a for a in analyzer.suggest_candidates(draft, limit=40) if a.champion.id != mine]
            entries += self._ranked_entries(suggestions, can_pick=me is not None)

        missing = [names.get(i, i) for i in analyzer.missing_profiles(draft) if i != mine]
        if missing:
            notes.append("Sin perfil (no cuentan en el análisis): " + escape(", ".join(missing)) + ".")
        notes.append(
            "Basado en perfiles cualitativos (editoriales, revisados por ti o estimados automáticamente) y, si "
            "hay muestra suficiente, en estadísticas observadas del enfrentamiento directo. La puntuación no es "
            "un win rate."
        )
        self.analysis_notes.setText("<br>".join(notes))

        self._analyses = [a for a, _, _ in entries]
        self._render_cards(entries)
        self._render_ban_suggestions(draft)
        focus = mine or (self._analyses[0].champion.id if self._analyses else None)
        self._render_matchup(draft, focus, mine is None)
        self._render_build(draft, focus, mine is None)
        allies, enemies = analyzer.compositions(draft)
        self.ally_summary.setText(self._team_html("Tu equipo", allies))
        self.enemy_summary.setText(self._team_html("Equipo enemigo", enemies))

    def _render_cards(self, entries: list[tuple[CandidateAnalysis, str | None, bool]]) -> None:
        while self.cards_layout.count():
            widget = self.cards_layout.takeAt(0).widget()
            if widget is not None:
                # Ocultar y soltar antes de borrar: deleteLater no actúa al instante
                # y la tarjeta vieja seguiría dibujándose encima de la nueva.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        if not entries:
            self.cards_layout.addWidget(notice_label("No hay candidatos con perfil para esta situación."), 0, 0)
            return
        for index, (analysis, caption, can_pick) in enumerate(entries):
            card_widget = RecommendationCard(analysis, self.portraits, caption, can_pick)
            card_widget.pick_requested.connect(self.pick_for_me)
            self.cards_layout.addWidget(card_widget, index // CARD_COLUMNS, index % CARD_COLUMNS)

    @staticmethod
    def _has_experience(analysis: CandidateAnalysis) -> bool:
        return any(f.key == "comfort" and f.kind is EvidenceKind.OBSERVED for f in analysis.factors)

    def _ranked_entries(self, suggestions: list[CandidateAnalysis], can_pick: bool):
        """Ordena y etiqueta las sugerencias con honestidad: «para ti» solo si lo juegas."""
        if not suggestions:
            return []
        best = suggestions[0]
        pool = [a for a in suggestions if self._has_experience(a)]
        if self._has_experience(best) or not pool:
            caption = "Mejor opción para ti" if self._has_experience(best) else "Mejor puntuación"
            ordered = [(best, caption)] + [(a, "Alternativa") for a in suggestions[1:SUGGESTIONS]]
        else:
            # El mejor de tu repertorio primero; después, el mejor en general y el resto.
            ordered = [(pool[0], "Mejor de tu repertorio"), (best, "Mejor puntuación general")]
            ordered += [(a, "Alternativa") for a in suggestions[1:] if a is not pool[0]][:SUGGESTIONS - 2]
        return [(a, caption, can_pick) for a, caption in ordered]

    def _render_matchup(self, draft: DraftState, champion_id: str | None, is_suggestion: bool) -> None:
        names = self._names()
        profiles = {p.id: p for p in self.ctx.analyzer.champions}
        enemy_roles = assign_enemy_roles(draft.enemies, profiles)
        role = draft.my_role

        # Gankeos: si juegas jungla, qué línea conviene; si no, el peligro del jungla rival.
        self.gank_heading.setVisible(role is not None)
        self.gank_box.setVisible(role is not None)
        if role is Role.JUNGLE:
            self.gank_heading.setText("¿Qué línea gankear?")
            allies = {p.role: profiles[p.champion_id] for p in draft.allies
                      if p.role and p.champion_id in profiles}
            enemies = {r: profiles[c] for r, (c, _) in enemy_roles.items() if c in profiles}
            tags = {c.id: c.tags for c in self.ctx.catalog.champions}
            self.gank_label.setText(ganks_html(gank_options(allies, enemies, tags), names))
        elif role is not None:
            self.gank_heading.setText("Riesgo de gankeo")
            jungler = enemy_roles.get(Role.JUNGLE)
            if jungler and jungler[0] in profiles:
                self.gank_label.setText(danger_html(gank_danger(profiles.get(champion_id), profiles[jungler[0]]),
                                                    names))
            else:
                self.gank_label.setText("<i>Aún no se sabe quién es el jungla rival.</i>")

        rival = enemy_roles.get(role) if role else None
        self.matchup_heading.setText("Tu enfrentamiento" + (" (opción recomendada)" if is_suggestion else ""))
        if role is None:
            self.matchup_label.setText("<i>Indica tu posición para ver tu enfrentamiento directo.</i>")
            return
        if champion_id is None or champion_id not in profiles:
            self.matchup_label.setText("<i>Elige tu campeón para ver el enfrentamiento.</i>")
            return
        if rival is None or rival[0] not in profiles:
            self.matchup_label.setText(
                f"<i>Aún no se sabe quién es tu rival de {role.label}. En el draft en vivo, indica su posición "
                "en su casilla si la deduces.</i>")
            return
        enemy_id, deduced = rival
        stats = {c.id: c.base_stats for c in self.ctx.catalog.champions if c.base_stats}
        matchup = analyze_matchup(profiles[champion_id], profiles[enemy_id], role, stats, self.session.matches,
                                  self.session.matches_are_demo, self._gold_diffs(enemy_id))
        self.matchup_label.setText(matchup_html(matchup, names, deduced, self._enemy_tips.get(enemy_id)))
        self._load_tips(enemy_id)

    def _gold_diffs(self, enemy_id: str) -> dict[str, int]:
        """Diferencia de oro al minuto 10 contra ese rival, solo con timelines ya guardados (sin red)."""
        out = {}
        for m in self.session.matches:
            if m.lane_opponent != enemy_id or m.is_demo:
                continue
            if m.match_id not in self._gold_at_10:
                try:
                    analysis = self.ctx.matches.lane_analysis(m, download=False)
                except (KeyError, TypeError, ValueError):  # Timeline guardado con formato inesperado.
                    analysis = None
                snapshot = next((s for s in analysis.snapshots if s.minute == 10), None) if analysis else None
                self._gold_at_10[m.match_id] = snapshot.gold_diff if snapshot else None
            if self._gold_at_10[m.match_id] is not None:
                out[m.match_id] = self._gold_at_10[m.match_id]
        return out

    def _load_tips(self, enemy_id: str) -> None:
        if enemy_id in self._enemy_tips or enemy_id in self._tips_loading or not self.ctx.catalog.from_data_dragon:
            return
        self._tips_loading.add(enemy_id)

        def done(detail) -> None:
            self._tips_loading.discard(enemy_id)
            self._enemy_tips[enemy_id] = detail.enemy_tips if detail else []
            if self._enemy_tips[enemy_id]:
                self.update_analysis()

        def failed(_error: str) -> None:
            self._tips_loading.discard(enemy_id)
            self._enemy_tips[enemy_id] = []

        run_task(lambda: self.ctx.champion_detail(enemy_id), on_done=done, on_error=failed)

    def _render_build(self, draft: DraftState, champion_id: str | None, is_suggestion: bool) -> None:
        names = self._names()
        data = self.ctx.game_data
        if champion_id is None:
            self.build_heading.setText("Build")
            self.build_label.setText("<i>Elige tu campeón para ver su build.</i>")
            return
        name = names.get(champion_id, champion_id)
        self.build_heading.setText(f"Build para {name}" + (" (opción recomendada)" if is_suggestion else ""))
        if data is None:
            self.build_label.setText("<i>Las builds necesitan los datos de Data Dragon (objetos, runas y hechizos).</i>")
            return
        profiles = {p.id: p for p in self.ctx.analyzer.champions}
        enemies = analyze_team([profiles[p.champion_id] for p in draft.enemies if p.champion_id in profiles])
        advice = build_advice(champion_id, profiles.get(champion_id), draft.my_role, enemies, data,
                              self.session.matches)
        self.build_label.setText(build_advice_html(self.ctx, advice, self.session.matches_are_demo, compact=True)
                                 + f"<p style='color:{theme.MUTED}'>Más detalle en «Runas y builds». Las builds se "
                                   "basan en las características oficiales de los objetos, la composición rival y "
                                   "tus partidas; no en estadísticas globales.</p>")

    def _render_ban_suggestions(self, draft: DraftState) -> None:
        while self.ban_row.count():
            widget = self.ban_row.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        names = self._names()
        key_to_id = self.ctx.champion_keys()
        mastery_ids = [key_to_id[k] for k in self.session.mastery_champion_keys() if k in key_to_id]
        if draft.my_champion_id:
            pool = [draft.my_champion_id]
            basis = f"tu campeón ({names.get(draft.my_champion_id, draft.my_champion_id)})"
        else:
            pool = comfort_pool(self.session.matches, draft.my_role, mastery_ids)
            basis = ("tus campeones de confianza (" + ", ".join(names.get(c, c) for c in pool) + ")") if pool else ""
        taken = self._taken()
        suggestions = suggest_bans(
            draft.my_role, pool, self.session.matches, {p.id: p for p in self.ctx.analyzer.champions},
            imported=self.ctx.stats.imported, exclude=taken, limit=5,
        )
        if not pool:
            self.ban_note.setText("Indica tu campeón o carga tus partidas para personalizar los bloqueos.")
            return
        demo = " Tus partidas son FICTICIAS de demostración." if self.session.matches_are_demo else ""
        self.ban_note.setText(f"Pensados para {escape(basis)}. Pasa el ratón para ver los motivos.{demo}")
        if not suggestions:
            self.ban_note.setText(self.ban_note.text() + " No hay suficientes datos para sugerir bloqueos.")
            return
        for index, s in enumerate(suggestions):
            chip = QFrame()
            chip.setObjectName("card")
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(8, 6, 10, 6)
            chip_layout.setSpacing(8)
            portrait = QLabel()
            portrait.setPixmap(self.portraits.get(s.champion_id, 34))
            kinds = " + ".join(dict.fromkeys(k.label for k in s.kinds))
            text = QLabel(f"<b>{escape(names.get(s.champion_id, s.champion_id))}</b><br>"
                          f"<span style='color:{theme.MUTED}; font-size:8pt'>{escape(kinds)}</span>")
            chip_layout.addWidget(portrait)
            chip_layout.addWidget(text)
            chip_layout.addStretch()
            chip.setToolTip("\n".join(f"• {r}" for r in s.reasons))
            self.ban_row.addWidget(chip, index // BAN_COLUMNS, index % BAN_COLUMNS)

    @staticmethod
    def _team_html(title: str, team: TeamProfile) -> str:
        if not team.champion_ids:
            return f"<b>{title}</b><br><span style='color:#8b929c'>Sin campeones con perfil.</span>"
        strengths = "".join(f"<div>+ {escape(s)}</div>" for s in team.strengths) or "<div>Ninguna destacada.</div>"
        weaknesses = "".join(f"<div>− {escape(w)}</div>" for w in team.weaknesses) or "<div>Ninguna destacada.</div>"
        return (
            f"<b>{title}</b> <span style='color:#8b929c'>(inferencias)</span><br>"
            f"Daño: {team.physical_share:.0%} físico / {team.magic_share:.0%} mágico<br>"
            f"<span style='color:#8b929c'>Iniciación {team.engage} · Desenganche {team.disengage} · "
            f"Control {team.cc} · Temprano {team.early} · Escalado {team.scaling} · "
            f"Primera línea {team.frontline}</span>"
            f"<div style='margin-top:4px'><b>Fortalezas</b></div>{strengths}"
            f"<div style='margin-top:4px'><b>Debilidades</b></div>{weaknesses}"
        )

    def show_report(self) -> None:
        allies, enemies = self.ctx.analyzer.compositions(self.current_draft())
        sources = [self.ctx.dataset.source]
        if self.ctx.catalog.from_data_dragon:
            sources.append(self.ctx.catalog.source)
        dialog = QDialog(self)
        dialog.setWindowTitle("Informe completo del draft")
        dialog.resize(820, 680)
        browser = QTextBrowser()
        browser.setHtml(render_report(
            self._analyses, allies, enemies, sources, self.analysis_heading.text(),
        ))
        QVBoxLayout(dialog).addWidget(browser)
        dialog.exec()

    # --- Notificaciones de la ventana principal ----------------------------

    def on_catalog_changed(self) -> None:
        names = self._names()
        for slot in self.ally_slots + self.enemy_slots:
            if slot.champion_id:
                slot.set_champion(slot.champion_id, names.get(slot.champion_id, slot.champion_id))
            else:
                slot.refresh()
        self.grid.reload()
        self.update_analysis()

    def on_profile_changed(self) -> None:
        self.update_analysis()
