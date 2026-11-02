"""Pruebas de humo de la interfaz: crea la ventana sin mostrarla y usa el tablero."""

import pytest

from draftmind.app.bootstrap import build_context
from draftmind.app.config import Settings
from draftmind.domain.enums import Role

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    from draftmind.ui.main_window import MainWindow

    # ddragon_enabled=False: las pruebas nunca usan la red.
    ctx = build_context(Settings(data_dir=tmp_path, ddragon_enabled=False), in_memory_db=True)
    w = MainWindow(ctx)
    yield w
    w.close()


def set_role(view, role):
    view.my_role.setCurrentIndex(view.my_role.findData(role))


def test_ban_suggestions_appear_in_draft(window):
    view = window.draft_view
    set_role(view, Role.TOP)
    view.pick_for_me("Kayle")
    chips = [view.ban_row.itemAt(i).widget() for i in range(view.ban_row.count())]
    assert chips, "Debería haber al menos una sugerencia de bloqueo para Kayle"
    assert all(c.toolTip().startswith("•") for c in chips)  # Cada sugerencia explica sus motivos.
    assert "Kayle" in view.ban_note.text()


def test_profile_view_with_demo_matches(window):
    view = window.profile_view
    assert "Jugador Demo" in view.hero_title.text()
    assert "FICTICIOS" in view.hero_sub.text()
    assert view.table.rowCount() > 0
    assert view.tiles["games"].text() != "—"
    assert not view.refresh_button.isVisibleTo(view)  # Sin API key no se consulta el rango.


def test_navigation_switches_every_section(window):
    assert window.nav.count() == window.stack.count() == 11
    for row in range(window.nav.count()):
        window.nav.setCurrentRow(row)
        assert window.stack.currentIndex() == row


def test_without_data_dragon_uses_demo_catalog(window):
    assert not window.ctx.catalog.from_data_dragon
    assert window.draft_view.grid.list.count() == len(window.ctx.dataset.champions)


def test_suggestions_appear_without_api_key(window):
    view = window.draft_view
    set_role(view, Role.UTILITY)
    assert view.analysis_heading.text() == "Sugerencias para Soporte"
    assert view._analyses
    assert all(Role.UTILITY in a.champion.roles for a in view._analyses)


def test_board_fills_my_slot_then_advances(window):
    view = window.draft_view
    set_role(view, Role.MIDDLE)
    view.place_champion("Ahri")  # Sin casilla activa: va a tu casilla.
    me = view.my_slot()
    assert me.champion_id == "Ahri"
    assert view.analysis_heading.text() == "Tu elección y alternativas"
    assert view._analyses[0].champion.id == "Ahri"


def test_active_slot_receives_pick_and_taken_champions_are_disabled(window):
    view = window.draft_view
    enemy_top = view.enemy_slots[0]
    view.activate(enemy_top)
    view.place_champion("Darius")
    assert enemy_top.champion_id == "Darius"
    assert view.active_slot is view.enemy_slots[1]  # Avanza a la siguiente vacía.
    view.place_champion("Darius")  # Ya elegido: se ignora.
    assert view.enemy_slots[1].champion_id is None
    item = next(view.grid.list.item(i) for i in range(view.grid.list.count())
                if view.grid.list.item(i).text() == "Darius")
    assert not item.flags()  # Desactivado en la cuadrícula.


def test_clear_slot_and_pick_from_card(window):
    view = window.draft_view
    set_role(view, Role.TOP)
    view.pick_for_me("Malphite")
    assert view.my_slot().champion_id == "Malphite"
    view.clear_slot(view.my_slot())
    assert view.my_slot().champion_id is None


def test_profile_saved_from_settings_reaches_analyzer(window):
    settings_view = window.settings_view
    settings_view.role_checks[Role.JUNGLE].setChecked(True)
    settings_view.save_profile()
    assert Role.JUNGLE in window.ctx.analyzer.profile.main_roles
    assert settings_view.status.text() == "Perfil guardado."


def test_history_loads_fictional_demo_without_key(window):
    view = window.history_view
    assert window.session.matches_are_demo
    assert view.table.rowCount() == 14
    assert not view.load_button.isEnabled()  # Sin API key no se puede consultar la Riot API.
    view.result_filter.setCurrentIndex(view.result_filter.findData(True))
    assert all(m.win for m in window.session.filtered)


def test_history_selection_reaches_postgame(window):
    first = window.session.matches[0]
    window.session.match_selected.emit(first.match_id)
    assert window.analysis_view.selected.match_id == first.match_id
    assert "FICTICIAS" in window.analysis_view.demo_notice.text()
    assert window.analysis_view.observations.text()


def test_personal_stats_feed_counters(window):
    assert window.ctx.stats.personal is not None
    assert "FICTICIAS" in window.ctx.stats.personal.source.name
    view = window.counters_view
    view.mine.setCurrentIndex(view.mine.findData("Malphite"))
    assert view.history.rowCount() > 0  # Rivales observados en las partidas de demostración.


def test_strategy_follows_draft(window):
    draft = window.draft_view
    for slot, cid in zip(draft.ally_slots[:3], ("Malphite", "Amumu", "Orianna")):
        draft.activate(slot)
        draft.place_champion(cid)
    assert [p.champion_id for p in window.session.draft.allies] == ["Malphite", "Amumu", "Orianna"]
    assert "Reparto de daño" in window.strategy_view.ally_label.text()
    assert "3 campeones con perfil" in window.strategy_view.ally_label.text()


def test_builds_without_game_data_shows_notice(window):
    assert window.ctx.game_data is None
    assert window.builds_view.missing_data.isVisibleTo(window.builds_view)


def test_research_source_round_trip(window):
    view = window.research_view
    view.url.setText("https://developer.riotgames.com/docs/lol")
    view.title.setText("Documentación de LoL")
    view.save()
    assert view.table.rowCount() == 1
    assert view.table.item(0, 3).text() == "Sin verificar"
    view.url.setText("no es una url")
    view.save()
    assert "http" in view.status.text()


def test_live_draft_is_disabled_by_default(window):
    assert not window.ctx.app_settings.live_draft_enabled
    assert not window.draft_view.live_bar.isVisibleTo(window.draft_view)
    assert not window.draft_view._live_timer.isActive()


def test_live_draft_fills_board_without_names(window, tmp_path):
    from draftmind.integrations.champ_select import LiveDraft, LiveSlot
    from draftmind.services.live_draft_service import LiveState, LiveStatus

    view = window.draft_view
    window.ctx.app_settings.league_install_dir = tmp_path  # Sin lockfile: no hay cliente real.
    window.ctx.app_settings.live_draft_enabled = True
    view.configure_live()
    assert view.live_bar.isVisibleTo(view) and view._live_timer.isActive()

    draft = LiveDraft(
        me=LiveSlot(cell_id=2, champion_id="Ahri", is_intent=True, role=Role.MIDDLE),
        allies=[LiveSlot(cell_id=0, champion_id="Malphite", role=Role.TOP),
                LiveSlot(cell_id=4, champion_id="Janna", role=None)],
        enemies=[LiveSlot(cell_id=5, champion_id="Darius"), LiveSlot(cell_id=6)],
        bans=["Zed", "Leona"],
    )
    view.apply_live_status(LiveStatus(LiveState.CHAMP_SELECT, "Selección de campeones en curso.", draft))
    me = view.my_slot()
    assert me.role is Role.MIDDLE and me.champion_id == "Ahri" and me.champion_name == "Ahri"
    assert me.tentative and "sin confirmar" in me.detail.text()
    assert all(s.role is None for s in view.enemy_slots)
    assert view.ally_slots[0].champion_id == "Malphite"
    assert any(s.champion_id == "Janna" for s in view.ally_slots)
    assert view.enemy_slots[0].champion_id == "Darius" and view.enemy_slots[0].role is None
    assert window.session.draft.bans == ["Zed", "Leona"]
    assert all(a.champion.id not in {"Zed", "Leona"} for a in view._analyses)  # Bloqueados no se sugieren.

    # El rol enemigo que indica el usuario se conserva en la siguiente lectura.
    view.enemy_slots[0].role_box.setCurrentIndex(view.enemy_slots[0].role_box.findData(Role.TOP))
    updated = draft.model_copy(update={"enemies": [LiveSlot(cell_id=5, champion_id="Darius"),
                                                   LiveSlot(cell_id=6, champion_id="Zed")]})
    view.apply_live_status(LiveStatus(LiveState.CHAMP_SELECT, "Selección de campeones en curso.", updated))
    assert view.enemy_slots[0].role is Role.TOP

    # Durante la partida no se modifica el tablero.
    before = [s.champion_id for s in view.enemy_slots]
    view.apply_live_status(LiveStatus(LiveState.IN_GAME, "Partida en curso: no se actualiza."))
    assert [s.champion_id for s in view.enemy_slots] == before
    assert "Partida en curso" in view.live_status.text()

    window.ctx.app_settings.live_draft_enabled = False
    view.configure_live()
    assert not view._live_timer.isActive()


def test_live_blind_pick_without_my_position(window):
    """Caso real (01/11/2026): en selección a ciegas el cliente no asigna posición al jugador."""
    from draftmind.integrations.champ_select import LiveDraft, LiveSlot
    from draftmind.services.live_draft_service import LiveState, LiveStatus

    view = window.draft_view
    view.my_role.setCurrentIndex(view.my_role.findData(Role.MIDDLE))  # Lo que el usuario tenía elegido.
    window.ctx.app_settings.live_draft_enabled = True
    view._live_service = object()  # Basta con que no sea None para aceptar estados.
    draft = LiveDraft(
        me=LiveSlot(cell_id=0, role=None),
        allies=[LiveSlot(cell_id=1, champion_id="KogMaw", role=Role.BOTTOM),
                LiveSlot(cell_id=2, champion_id="XinZhao", role=Role.JUNGLE),
                LiveSlot(cell_id=3, champion_id="Veigar", role=Role.MIDDLE),
                LiveSlot(cell_id=4, champion_id="Lulu", role=Role.UTILITY)],
        enemies=[LiveSlot(cell_id=c) for c in range(5, 10)],
    )
    view.apply_live_status(LiveStatus(LiveState.CHAMP_SELECT, "Selección.", draft))
    assert view.my_slot().role is Role.TOP and view.my_slot().champion_id is None
    by_role = {s.role: s.champion_id for s in view.ally_slots}
    assert by_role[Role.MIDDLE] == "Veigar" and by_role[Role.BOTTOM] == "KogMaw"
    view._live_service = None


def test_riot_disclaimer_is_shown(window):
    from PySide6.QtWidgets import QLabel

    texts = " ".join(label.text() for label in window.dashboard.findChildren(QLabel))
    assert "isn't endorsed by Riot Games" in texts


def test_profile_editor_saves_and_resets(window):
    from draftmind.domain.enums import ProfileOrigin

    view = window.champions_view
    view.show_champion("Leona")
    view.set_editing(True)
    assert view.edit_panel.isVisibleTo(view)
    view.spins["engage"].setValue(1)
    view.save_profile()
    leona = window.ctx.analyzer.champion("Leona")
    assert leona.origin is ProfileOrigin.USER and leona.engage == 1
    assert "Revisado por ti" in view.origin_label.text()
    assert view.reset_button.isVisibleTo(view)

    window.ctx.champion_profiles.delete("Leona")  # Lo mismo que «Restablecer» sin el diálogo.
    window.ctx.rebuild_profiles()
    assert window.ctx.analyzer.champion("Leona").origin is ProfileOrigin.EDITORIAL


def test_champion_view_shows_profile_bars(window):
    view = window.champions_view
    view.show_champion("Leona")
    assert view.bars["engage"].value() == 3
    assert view.bars["engage"].isVisibleTo(view)
