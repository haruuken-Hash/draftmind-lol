"""Runas y builds: recomendaciones situacionales y exploradores de datos oficiales."""

from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from draftmind.analysis.build_analyzer import build_advice
from draftmind.analysis.composition_analyzer import analyze_team
from draftmind.app.bootstrap import AppContext
from draftmind.domain.enums import Role
from draftmind.ui import theme
from draftmind.ui.portraits import PortraitProvider
from draftmind.ui.session import AppSession
from draftmind.ui.widgets import combo_role, notice_label, subtitle_label, title_label

ITEM_TAG_LABELS = {
    "Armor": "Armadura", "SpellBlock": "Resistencia mágica", "Health": "Vida", "Damage": "Daño de ataque",
    "SpellDamage": "Poder de habilidad", "AttackSpeed": "Velocidad de ataque", "CriticalStrike": "Crítico",
    "Boots": "Botas", "Tenacity": "Tenacidad", "ArmorPenetration": "Penetración de armadura",
    "MagicPenetration": "Penetración mágica", "AbilityHaste": "Aceleración de habilidades",
    "LifeSteal": "Robo de vida", "Mana": "Maná", "Active": "Efecto activo",
}


class BuildsView(QWidget):
    def __init__(self, ctx: AppContext, session: AppSession, portraits: PortraitProvider,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.portraits = portraits

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.addWidget(title_label("Runas y builds"))
        layout.addWidget(subtitle_label(
            "Las recomendaciones estratégicas salen de la composición enemiga del «Draft». Las configuraciones "
            "frecuentes salen de tus partidas. Los datos de objetos, runas y hechizos son oficiales de Data Dragon."
        ))
        self.missing_data = notice_label(
            "Todavía no hay datos de objetos, runas y hechizos. Se descargan de Data Dragon al arrancar con conexión."
        )
        layout.addWidget(self.missing_data)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._recommendations_tab(), "Recomendaciones")
        self.tabs.addTab(self._items_tab(), "Objetos")
        self.tabs.addTab(self._browser_tab("runes"), "Runas")
        self.tabs.addTab(self._browser_tab("spells"), "Hechizos")
        layout.addWidget(self.tabs, 1)

        session.draft_changed.connect(self.refresh)
        session.matches_changed.connect(self.refresh)
        self.on_catalog_changed()

    # --- Pestañas -------------------------------------------------------------

    def _recommendations_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.champion = QComboBox()
        self.role = QComboBox()
        self.role.addItem("Sin indicar", None)
        for r in Role:
            self.role.addItem(r.label, r)
        self.use_draft = QCheckBox("Usar la composición enemiga del draft")
        self.use_draft.setChecked(True)
        row = QHBoxLayout()
        row.addWidget(QLabel("Campeón:"))
        row.addWidget(self.champion, 2)
        row.addWidget(QLabel("Posición:"))
        row.addWidget(self.role, 1)
        row.addWidget(self.use_draft)
        layout.addLayout(row)
        self.report = QLabel()
        self.report.setWordWrap(True)
        self.report.setTextFormat(Qt.TextFormat.RichText)
        self.report.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.report)
        layout.addWidget(scroll, 1)
        self.champion.currentIndexChanged.connect(self.refresh)
        self.role.currentIndexChanged.connect(self.refresh)
        self.use_draft.toggled.connect(self.refresh)
        return tab

    def _items_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.item_search = QLineEdit(placeholderText="Buscar objeto…")
        self.item_tag = QComboBox()
        self.item_tag.addItem("Todas las estadísticas", None)
        for tag, label in ITEM_TAG_LABELS.items():
            self.item_tag.addItem(label, tag)
        row = QHBoxLayout()
        row.addWidget(self.item_search, 2)
        row.addWidget(self.item_tag, 1)
        layout.addLayout(row)
        self.item_list = QListWidget()
        self.item_detail = QTextBrowser()
        splitter = QSplitter()
        splitter.addWidget(self.item_list)
        splitter.addWidget(self.item_detail)
        splitter.setSizes([320, 520])
        layout.addWidget(splitter, 1)
        self.item_search.textChanged.connect(self._fill_items)
        self.item_tag.currentIndexChanged.connect(self._fill_items)
        self.item_list.currentItemChanged.connect(self._show_item)
        return tab

    def _browser_tab(self, kind: str) -> QWidget:
        browser = QTextBrowser()
        setattr(self, f"{kind}_browser", browser)
        return browser

    # --- Utilidades ---------------------------------------------------------

    def _img(self, relative: str | None, size: int = 26) -> str:
        path = self.ctx.catalogs.client.cached_image(relative) if relative else None
        if path is None:
            return ""
        return f"<img src='{Path(path).as_posix()}' width='{size}' height='{size}'> "

    def _item_img(self, item_id: str | int, size: int = 26) -> str:
        data = self.ctx.game_data
        return self._img(f"{data.version}/img/item/{item_id}.png", size) if data else ""

    # --- Contenido ----------------------------------------------------------------

    def on_catalog_changed(self) -> None:
        current = self.champion.currentData()
        self.champion.blockSignals(True)
        self.champion.clear()
        for c in self.ctx.catalog.champions:
            self.champion.addItem(QIcon(self.portraits.get(c.id, 20)), c.name, c.id)
        index = self.champion.findData(current or "Malphite")
        self.champion.setCurrentIndex(max(index, 0))
        self.champion.blockSignals(False)
        data = self.ctx.game_data
        self.missing_data.setVisible(data is None)
        self._fill_items()
        self._fill_runes()
        self._fill_spells()
        self.refresh()

    def refresh(self) -> None:
        data = self.ctx.game_data
        champion_id = self.champion.currentData()
        if data is None or not champion_id:
            self.report.setText("<i>Sin datos de Data Dragon todavía.</i>")
            return
        profiles = {c.id: c for c in self.ctx.analyzer.champions}
        draft = self.session.draft
        enemy_profiles = [profiles[p.champion_id] for p in draft.enemies if p.champion_id in profiles]
        enemies = analyze_team(enemy_profiles if self.use_draft.isChecked() else [])
        advice = build_advice(champion_id, profiles.get(champion_id), combo_role(self.role), enemies, data,
                              self.session.matches)
        names = {c.id: c.name for c in self.ctx.catalog.champions}
        muted = theme.MUTED

        parts = []
        if self.use_draft.isChecked():
            listed = ", ".join(names.get(p.champion_id, p.champion_id) for p in draft.enemies) or "ninguno"
            parts.append(f"<p style='color:{muted}'>Enemigos del draft: {escape(listed)}</p>")

        parts.append("<h3>Recomendaciones estratégicas</h3>")
        if advice.needs:
            for need in advice.needs:
                items = "".join(
                    f"<div>{self._item_img(i.id)}<b>{escape(i.name)}</b> · {i.total_gold} de oro — "
                    f"<span style='color:{muted}'>{escape(i.plaintext)}</span></div>"
                    for i in need.items
                ) or f"<div style='color:{muted}'>No se encontraron objetos con esas características.</div>"
                parts.append(f"<p><b>{escape(need.title)}</b> <i>[{need.kind.label}]</i><br>{escape(need.reason)}</p>"
                             f"{items}<p style='color:{muted}'>Ejemplos según etiquetas oficiales; no son "
                             "la única opción ni necesariamente la mejor.</p>")
        else:
            parts.append(f"<p style='color:{muted}'>Sin necesidades situacionales detectadas con los enemigos indicados.</p>")

        parts.append("<h3>Runas</h3>")
        for rune in advice.runes:
            keystones = "".join(
                f"<div>{self._img('img/' + k.icon, 24)}<b>{escape(k.name)}</b>: "
                f"<span style='color:{muted}'>{escape(k.short_desc)}</span></div>"
                for k in rune.path.keystones
            )
            parts.append(f"<p>{self._img('img/' + rune.path.icon, 22)}<b>{escape(rune.path.name)}</b> "
                         f"<i>[{rune.kind.label}]</i><br>{escape(rune.reason)}</p>{keystones}")
        if not advice.runes:
            parts.append(f"<p style='color:{muted}'>Sin orientación de runas para este campeón.</p>")

        parts.append("<h3>Hechizos de invocador</h3>")
        spells = self.ctx.game_data.spells
        for s in advice.spells:
            image = next((sp.image_file for sp in spells if sp.id == s.spell_id), None)
            img = self._img(f"{data.version}/img/spell/{image}", 24) if image else ""
            parts.append(f"<div>{img}<b>{escape(s.name)}</b>: {escape(s.reason)} <i>[Sugerencia educativa]</i></div>")

        parts.append(f"<h3>Tus configuraciones frecuentes ({advice.personal_games} partidas)</h3>")
        if advice.frequent_items:
            demo = " (partidas FICTICIAS de demostración)" if self.session.matches_are_demo else ""
            parts.append(f"<p style='color:{muted}'>Estadística observada en tus partidas{demo}. "
                         "Frecuencia de uso, no eficacia.</p>")
            for f in advice.frequent_items:
                parts.append(f"<div>{self._item_img(f.item_id)}<b>{escape(f.name)}</b>: en {f.games} partidas "
                             f"({f.wins} victorias)</div>")
            for name, games, wins in advice.frequent_keystones:
                parts.append(f"<div>Runa clave <b>{escape(name)}</b>: {games} partidas ({wins} victorias)</div>")
        parts.append("".join(f"<p style='color:{muted}'>Nota: {escape(n)}</p>" for n in advice.notes))
        self.report.setText("".join(parts))

    def _fill_items(self) -> None:
        self.item_list.clear()
        data = self.ctx.game_data
        if data is None:
            return
        text = self.item_search.text().strip().lower()
        tag = self.item_tag.currentData()
        for item in data.items:
            if text and text not in item.name.lower():
                continue
            if tag and tag not in item.tags:
                continue
            entry = QListWidgetItem(QIcon(self.portraits.item(item.id, 28)), f"{item.name}  ·  {item.total_gold}")
            entry.setData(Qt.ItemDataRole.UserRole, item.id)
            self.item_list.addItem(entry)

    def _show_item(self, current: QListWidgetItem | None) -> None:
        data = self.ctx.game_data
        if current is None or data is None:
            return
        item = data.item(current.data(Qt.ItemDataRole.UserRole))
        tags = ", ".join(ITEM_TAG_LABELS.get(t, t) for t in item.tags)
        components = ", ".join(data.item_name(c) for c in item.builds_from) or "ninguno"
        description = escape(item.description).replace("\n", "<br>")
        self.item_detail.setHtml(
            f"<h2>{self._item_img(item.id, 40)}{escape(item.name)}</h2>"
            f"<p><b>Coste total:</b> {item.total_gold} de oro<br><b>Características:</b> {escape(tags)}<br>"
            f"<b>Se construye con:</b> {escape(components)}</p><p>{description}</p>"
            f"<p style='color:{theme.MUTED}'>Fuente: Data Dragon {escape(data.version)} (dato oficial).</p>"
        )

    def _fill_runes(self) -> None:
        data = self.ctx.game_data
        if data is None:
            self.runes_browser.setHtml("<i>Sin datos.</i>")
            return
        html = []
        for path in data.rune_paths:
            html.append(f"<h2>{self._img('img/' + path.icon, 28)}{escape(path.name)}</h2><h4>Runas clave</h4>")
            html += [f"<p>{self._img('img/' + k.icon, 24)}<b>{escape(k.name)}</b>: {escape(k.short_desc)}</p>"
                     for k in path.keystones]
            for n, slot in enumerate(path.minor_slots, start=1):
                html.append(f"<h4>Fila {n}</h4>")
                html += [f"<p><b>{escape(r.name)}</b>: {escape(r.short_desc)}</p>" for r in slot]
        self.runes_browser.setHtml("".join(html))

    def _fill_spells(self) -> None:
        data = self.ctx.game_data
        if data is None:
            self.spells_browser.setHtml("<i>Sin datos.</i>")
            return
        html = [
            f"<p>{self._img(f'{data.version}/img/spell/{s.image_file}', 32)}<b>{escape(s.name)}</b>"
            f"{f' · enfriamiento {s.cooldown:.0f} s' if s.cooldown else ''}<br>{escape(s.description)}</p>"
            for s in data.spells
        ]
        self.spells_browser.setHtml("".join(html))
