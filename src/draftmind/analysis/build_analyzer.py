"""Recomendaciones de objetos, runas y hechizos.

Tres niveles que nunca se mezclan:
- Recomendaciones ESTRATÉGICAS: necesidades que sugiere la composición
  enemiga (inferencias). Los objetos se eligen por sus etiquetas oficiales de
  Data Dragon (Armor, SpellBlock, Tenacity...); describen qué hace cada
  objeto, no que sea el óptimo.
- Configuraciones FRECUENTES: lo que tú has usado con ese campeón (datos
  observados de tus partidas).
- Eficacia ESTADÍSTICA: solo se menciona si hay muestra suficiente; con tus
  partidas casi nunca la hay, y se dice así.
No se inventan tasas de victoria de builds.
"""

from collections import Counter

from pydantic import BaseModel

from draftmind.analysis.composition_analyzer import HIGH_CC, HIGH_ENGAGE
from draftmind.analysis.confidence import MIN_SAMPLE
from draftmind.domain.enums import DamageType, EvidenceKind, Role
from draftmind.domain.models import ChampionProfile, GameData, ItemInfo, MatchSummary, RunePathInfo, TeamProfile

DAMAGE_CONCENTRATION = 0.7
HIGH_FRONTLINE = 6
EXAMPLES = 4


class ItemNeed(BaseModel):
    title: str
    reason: str
    kind: EvidenceKind
    items: list[ItemInfo]


class RuneAdvice(BaseModel):
    path: RunePathInfo
    reason: str
    kind: EvidenceKind = EvidenceKind.EDUCATIONAL


class SpellAdvice(BaseModel):
    spell_id: str
    name: str
    reason: str


class FrequentItem(BaseModel):
    name: str
    item_id: int
    games: int
    wins: int


class BuildAdvice(BaseModel):
    needs: list[ItemNeed]
    runes: list[RuneAdvice]
    spells: list[SpellAdvice]
    frequent_items: list[FrequentItem]
    frequent_keystones: list[tuple[str, int, int]]  # (nombre, partidas, victorias)
    personal_games: int
    notes: list[str]


ALLY_WORDS = ("aliad", "ally", "allies")  # Objetos pensados para proteger a otros (soporte).


def _is_ally_item(item: ItemInfo) -> bool:
    text = f"{item.plaintext} {item.description}".lower()
    return any(word in text for word in ALLY_WORDS)


def _items_with(data: GameData, any_tags: set[str], champion: ChampionProfile | None,
                boots: bool | None = None, role: Role | None = None) -> list[ItemInfo]:
    """Objetos con alguna de las etiquetas, compatibles con el campeón y su posición.

    Orden: primero los que cumplen más etiquetas buscadas (y, para tanques,
    los que además dan vida); a igualdad, los más baratos. Los objetos
    centrados en aliados solo se proponen al soporte.
    """
    offensive_magic = {"SpellDamage"}
    offensive_physical = {"Damage", "CriticalStrike", "AttackSpeed"}
    # Tanque puro: primera línea máxima. Los luchadores también quieren daño.
    tank = champion is not None and champion.frontline >= 3
    own_offense: set[str] = set()
    if champion is not None:
        own_offense = {DamageType.MAGIC: offensive_magic, DamageType.PHYSICAL: offensive_physical}.get(
            champion.damage_type, offensive_magic | offensive_physical)
    scored = []
    for item in data.items:
        tags = set(item.tags)
        if not tags & any_tags:
            continue
        if boots is not None and ("Boots" in tags) != boots:
            continue
        if role is not Role.UTILITY and _is_ally_item(item):
            continue
        if champion is not None and not tank:
            if champion.damage_type is DamageType.MAGIC and tags & offensive_physical and not tags & offensive_magic:
                continue
            if champion.damage_type is DamageType.PHYSICAL and tags & offensive_magic and not tags & offensive_physical:
                continue
        if tank and tags & (offensive_magic | offensive_physical) and "Health" not in tags:
            continue  # Para un tanque, objetos de daño sin aguante no encajan.
        relevance = len(tags & any_tags)
        if tank and "Health" in tags:
            relevance += 1
        elif not tank and tags & own_offense:
            relevance += 1  # Resistencia + el tipo de daño del campeón.
        scored.append((-relevance, item.total_gold, item))
    return [item for *_, item in sorted(scored, key=lambda t: (t[0], t[1]))][:EXAMPLES]


def item_needs(champion: ChampionProfile | None, enemies: TeamProfile, data: GameData,
               role: Role | None = None) -> list[ItemNeed]:
    needs: list[ItemNeed] = []
    if not enemies.champion_ids:
        return needs
    if enemies.physical_share >= DAMAGE_CONCENTRATION:
        needs.append(ItemNeed(
            title="Armadura", kind=EvidenceKind.INFERENCE,
            reason=f"El {enemies.physical_share:.0%} del daño enemigo es físico según los perfiles.",
            items=_items_with(data, {"Armor"}, champion, boots=False, role=role)
            + _items_with(data, {"Armor"}, None, boots=True, role=role)[:1],
        ))
    elif enemies.magic_share >= DAMAGE_CONCENTRATION:
        needs.append(ItemNeed(
            title="Resistencia mágica", kind=EvidenceKind.INFERENCE,
            reason=f"El {enemies.magic_share:.0%} del daño enemigo es mágico según los perfiles.",
            items=_items_with(data, {"SpellBlock", "MagicResist"}, champion, boots=False, role=role)
            + _items_with(data, {"SpellBlock", "MagicResist"}, None, boots=True, role=role)[:1],
        ))
    if enemies.cc >= HIGH_CC:
        needs.append(ItemNeed(
            title="Tenacidad", kind=EvidenceKind.INFERENCE,
            reason=f"El equipo enemigo suma mucho control de masas ({enemies.cc} en los perfiles).",
            items=_items_with(data, {"Tenacity"}, champion, role=role),
        ))
    fragile = champion is not None and champion.frontline == 0
    if enemies.engage >= HIGH_ENGAGE and fragile:
        needs.append(ItemNeed(
            title="Supervivencia", kind=EvidenceKind.INFERENCE,
            reason="Mucha iniciación enemiga contra un campeón frágil: los objetos con vida o efectos activos "
                   "pueden darte margen.",
            items=_items_with(data, {"Health", "Active"}, champion, boots=False, role=role),
        ))
    if enemies.frontline >= HIGH_FRONTLINE and champion is not None and champion.frontline < 2:
        tag = "MagicPenetration" if champion.damage_type is DamageType.MAGIC else "ArmorPenetration"
        needs.append(ItemNeed(
            title="Penetración", kind=EvidenceKind.INFERENCE,
            reason="El rival tiene mucha primera línea: la penetración ayuda contra objetivos resistentes.",
            items=_items_with(data, {tag}, champion, role=role),
        ))
    return needs


# Orientación general (no estadística) por árbol de runas, usando la clave oficial.
_PATH_RULES = [
    ("Resolve", lambda c: c.frontline >= 2, "aporta aguante, adecuado para campeones de primera línea"),
    ("Precision", lambda c: c.damage_type is not DamageType.MAGIC and c.scaling >= 2 and c.frontline < 2,
     "favorece el daño sostenido, útil para quien escala con ataques"),
    ("Domination", lambda c: c.early >= 2 and c.frontline < 2, "premia la presión temprana y el daño en ráfaga"),
    ("Sorcery", lambda c: c.damage_type is DamageType.MAGIC or c.disengage >= 2,
     "potencia habilidades y utilidad, común en magos y apoyos"),
    ("Inspiration", lambda c: True, "aporta utilidad y alternativas creativas como árbol secundario"),
]


def rune_advice(champion: ChampionProfile | None, data: GameData) -> list[RuneAdvice]:
    if champion is None:
        return []
    by_key = {p.key: p for p in data.rune_paths}
    advice = []
    for key, rule, why in _PATH_RULES:
        if key in by_key and rule(champion):
            advice.append(RuneAdvice(
                path=by_key[key],
                reason=f"Orientación general: {by_key[key].name} {why}. No es una estadística de rendimiento.",
            ))
    return advice[:3]


# Hechizos habituales por posición (orientación educativa) con su ID oficial.
_ROLE_SPELLS = {
    Role.TOP: [("SummonerTeleport", "permite volver a la línea o unirse a peleas lejanas"),
               ("SummonerDot", "más presión para asesinar en la línea")],
    Role.JUNGLE: [("SummonerSmite", "necesario para despejar la jungla y disputar objetivos")],
    Role.MIDDLE: [("SummonerDot", "presión de asesinato en la línea"),
                  ("SummonerTeleport", "movilidad por el mapa"),
                  ("SummonerBarrier", "protección contra ráfagas")],
    Role.BOTTOM: [("SummonerHeal", "sostén para ti y tu soporte"),
                  ("SummonerBarrier", "protección contra ráfagas")],
    Role.UTILITY: [("SummonerDot", "presión en las peleas de la línea"),
                   ("SummonerExhaust", "reduce el daño de un rival peligroso")],
}


def spell_advice(role: Role | None, enemies: TeamProfile, data: GameData) -> list[SpellAdvice]:
    wanted = [("SummonerFlash", "movilidad de escape o persecución; se usa en casi todas las posiciones")]
    wanted += _ROLE_SPELLS.get(role, [])
    if enemies.cc >= HIGH_CC and role is Role.BOTTOM:
        wanted.append(("SummonerBoost", "elimina controles de masas; el rival tiene mucho"))
    by_id = {s.id: s for s in data.spells}
    return [SpellAdvice(spell_id=sid, name=by_id[sid].name, reason=why) for sid, why in wanted if sid in by_id]


def build_advice(
    champion_id: str,
    champion: ChampionProfile | None,
    role: Role | None,
    enemies: TeamProfile,
    data: GameData,
    matches: list[MatchSummary],
) -> BuildAdvice:
    notes: list[str] = []
    mine = [m for m in matches if m.champion_id == champion_id and m.win is not None]
    item_counter: Counter[int] = Counter()
    item_wins: Counter[int] = Counter()
    keystones: Counter[int] = Counter()
    keystone_wins: Counter[int] = Counter()
    for m in mine:
        for item_id in set(m.items):
            if data.item(item_id):  # Solo objetos completos, sin componentes ni abalorios.
                item_counter[item_id] += 1
                item_wins[item_id] += int(bool(m.win))
        if m.keystone_id:
            keystones[m.keystone_id] += 1
            keystone_wins[m.keystone_id] += int(bool(m.win))

    frequent = [FrequentItem(name=data.item_name(i), item_id=i, games=n, wins=item_wins[i])
                for i, n in item_counter.most_common(6)]
    frequent_keys = [((r.name if (r := data.rune(k)) else f"Runa #{k}"), n, keystone_wins[k])
                     for k, n in keystones.most_common(3)]

    if not mine:
        notes.append("No hay partidas tuyas con este campeón: no hay configuraciones frecuentes que mostrar.")
    elif len(mine) < MIN_SAMPLE:
        notes.append(f"Tus {len(mine)} partidas con este campeón muestran qué sueles usar, pero no bastan para "
                     f"medir qué configuración es más eficaz (harían falta al menos {MIN_SAMPLE}).")
    if champion is None:
        notes.append("El campeón no tiene perfil cualitativo: no hay orientación de runas.")
    if not enemies.champion_ids:
        notes.append("Añade enemigos en «Draft» para obtener recomendaciones situacionales.")
    notes.append("No se evalúa la curación enemiga ni los escudos: los perfiles no incluyen esos datos.")

    return BuildAdvice(
        needs=item_needs(champion, enemies, data, role),
        runes=rune_advice(champion, data),
        spells=spell_advice(role, enemies, data),
        frequent_items=frequent,
        frequent_keystones=frequent_keys,
        personal_games=len(mine),
        notes=notes,
    )
