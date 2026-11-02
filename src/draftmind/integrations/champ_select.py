"""Interpretación de la sesión de selección de campeones del cliente.

El formato de /lol-champ-select/v1/session NO está documentado por Riot; se
sigue la estructura descrita por proyectos de la comunidad y se lee de forma
defensiva (cualquier campo ausente o con otro tipo se ignora):
- localPlayerCellId: casilla del jugador local.
- myTeam / theirTeam: listas con cellId, championId (0 = sin elegir),
  championPickIntent (campeón «en hover») y assignedPosition (top, jungle,
  middle, bottom, utility o vacío).
- bans.myTeamBans / bans.theirTeamBans y actions[][] de tipo "ban"
  completadas: campeones bloqueados.

Privacidad y política de Riot: NO se lee ningún campo de nombre ni de
identificador de jugador (gameName, summonerId, puuid...). En la selección
de clasificatorias Riot exige anonimato, y este asistente no lo necesita.
Del equipo enemigo solo se usan los campeones ya elegidos, que el propio
cliente muestra; nunca sus intenciones.
"""

from typing import Any

from pydantic import BaseModel, Field

from draftmind.domain.enums import Role

POSITIONS = {
    "top": Role.TOP,
    "jungle": Role.JUNGLE,
    "middle": Role.MIDDLE,
    "bottom": Role.BOTTOM,
    "utility": Role.UTILITY,
}


class LiveSlot(BaseModel):
    cell_id: int
    champion_id: str | None = None
    is_intent: bool = False      # True si el campeón solo está «en hover», sin confirmar.
    role: Role | None = None


class LiveDraft(BaseModel):
    me: LiveSlot | None = None
    allies: list[LiveSlot] = Field(default_factory=list)   # Sin incluir al jugador local.
    enemies: list[LiveSlot] = Field(default_factory=list)
    bans: list[str] = Field(default_factory=list)
    unknown_champion_keys: list[int] = Field(default_factory=list)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _dicts(value: Any) -> list[dict]:
    """Elementos de una lista que sean diccionarios (el resto se ignora)."""
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def parse_session(raw: dict, key_to_id: dict[int, str]) -> LiveDraft:
    unknown: set[int] = set()

    def champion(key: Any) -> str | None:
        key = _int(key)
        if not key or key <= 0:
            return None
        if key not in key_to_id:
            unknown.add(key)
            return None
        return key_to_id[key]

    local_cell = _int(raw.get("localPlayerCellId"))
    me, allies = None, []
    for player in _dicts(raw.get("myTeam")):
        cell = _int(player.get("cellId"))
        if cell is None:
            continue
        picked = champion(player.get("championId"))
        intent = None if picked else champion(player.get("championPickIntent"))
        position = player.get("assignedPosition")
        slot = LiveSlot(
            cell_id=cell,
            champion_id=picked or intent,
            is_intent=picked is None and intent is not None,
            role=POSITIONS.get(position.lower()) if isinstance(position, str) else None,
        )
        if cell == local_cell:
            me = slot
        else:
            allies.append(slot)

    enemies = []
    for player in _dicts(raw.get("theirTeam")):
        cell = _int(player.get("cellId"))
        if cell is None:
            continue
        enemies.append(LiveSlot(cell_id=cell, champion_id=champion(player.get("championId"))))

    ban_keys: list[Any] = []
    bans = raw.get("bans") if isinstance(raw.get("bans"), dict) else {}
    for side in ("myTeamBans", "theirTeamBans"):
        if isinstance(bans.get(side), list):
            ban_keys += bans[side]
    for turn in raw.get("actions") if isinstance(raw.get("actions"), list) else []:
        for action in _dicts(turn):
            if action.get("type") == "ban" and action.get("completed") is True:
                ban_keys.append(action.get("championId"))
    banned = []
    for key in ban_keys:
        champion_id = champion(key)
        if champion_id and champion_id not in banned:
            banned.append(champion_id)

    return LiveDraft(
        me=me,
        allies=sorted(allies, key=lambda s: s.cell_id),
        enemies=sorted(enemies, key=lambda s: s.cell_id),
        bans=banned,
        unknown_champion_keys=sorted(unknown),
    )
