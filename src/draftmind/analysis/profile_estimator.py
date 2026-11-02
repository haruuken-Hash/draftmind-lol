"""Estimación automática de perfiles cualitativos a partir de Data Dragon.

Sirve para que los campeones sin perfil escrito a mano participen en el
análisis. Es una APROXIMACIÓN con reglas simples, marcada siempre como
«Estimación automática», y tiene menos peso que un perfil editorial o uno
revisado por el usuario (ver draft_analyzer.ESTIMATED_WEIGHT).

Datos oficiales usados:
- tags: clases del campeón (Fighter, Tank, Mage, Assassin, Marksman, Support).
  La primera es la principal.
- info: valoraciones 0-10 de ataque, defensa, magia y dificultad que muestra
  el propio juego.
- stats.attackrange: alcance (cuerpo a cuerpo si es menor de 300).

Límites conocidos: los datos oficiales no dicen qué campeones van a JUNGLA,
ni nada concreto sobre sus habilidades (control, iniciación...). Esas partes
salen de la clase y son las menos fiables.
"""

from draftmind.domain.enums import DamageType, ProfileOrigin, Role
from draftmind.domain.models import ChampionInfo, ChampionProfile

MELEE_RANGE = 300

# Valores base por clase principal: engage, disengage, cc, early, scaling, resource_dependence.
_BY_CLASS = {
    "Tank":     dict(engage=2, disengage=0, cc=3, early=1, scaling=2, resource_dependence=1),
    "Fighter":  dict(engage=1, disengage=0, cc=1, early=2, scaling=1, resource_dependence=2),
    "Assassin": dict(engage=1, disengage=0, cc=0, early=2, scaling=1, resource_dependence=2),
    "Mage":     dict(engage=0, disengage=1, cc=2, early=1, scaling=2, resource_dependence=2),
    "Marksman": dict(engage=0, disengage=0, cc=1, early=1, scaling=2, resource_dependence=3),
    "Support":  dict(engage=0, disengage=2, cc=2, early=1, scaling=2, resource_dependence=0),
}


def _clamp(value: int, low: int = 0, high: int = 3) -> int:
    return max(low, min(high, value))


def _roles(tags: list[str]) -> list[Role]:
    """Posiciones probables según la clase. La jungla no se puede deducir."""
    main = tags[0] if tags else ""
    roles = {
        "Marksman": [Role.BOTTOM],
        "Support": [Role.UTILITY],
        "Tank": [Role.TOP],
        "Fighter": [Role.TOP],
        "Assassin": [Role.MIDDLE],
        "Mage": [Role.MIDDLE],
    }.get(main, [])
    if "Support" in tags and Role.UTILITY not in roles:
        roles.append(Role.UTILITY)
    return roles


def _damage_type(info: ChampionInfo) -> DamageType:
    attack, magic = info.attack or 0, info.magic or 0
    if magic >= attack + 3:
        return DamageType.MAGIC
    if attack >= magic + 3:
        return DamageType.PHYSICAL
    return DamageType.MIXED


def _difficulty(official: int | None) -> int:
    """Dificultad oficial 1-10 -> escala 1-3 (1-4: baja, 5-7: media, 8-10: alta)."""
    if not official:
        return 2
    return 1 if official <= 4 else (2 if official <= 7 else 3)


def can_estimate(info: ChampionInfo) -> bool:
    return bool(info.tags) and info.defense is not None


def estimate_profile(info: ChampionInfo) -> ChampionProfile:
    tags = info.tags
    main = tags[0] if tags else "Fighter"
    base = dict(_BY_CLASS.get(main, _BY_CLASS["Fighter"]))
    melee = (info.attack_range or 0) < MELEE_RANGE
    defense = info.defense or 0

    # Primera línea: defensa oficial alta y cuerpo a cuerpo.
    frontline = 3 if defense >= 8 else 2 if defense >= 6 else 1 if defense >= 4 else 0
    if not melee:
        frontline -= 1
    # Un tanque de apoyo cuerpo a cuerpo suele iniciar las peleas.
    if "Tank" in tags and "Support" in tags and melee:
        base["engage"] = 3
    # Una clase secundaria de apoyo o mago añade algo de protección o control.
    if main != "Support" and "Support" in tags:
        base["disengage"] += 1
    if main != "Mage" and "Mage" in tags:
        base["cc"] += 1
    # Mucho ataque oficial en luchadores y asesinos: más presión temprana.
    if main in ("Fighter", "Assassin") and (info.attack or 0) >= 8:
        base["early"] += 1

    return ChampionProfile(
        id=info.id,
        name=info.name,
        origin=ProfileOrigin.ESTIMATED,
        roles=_roles(tags),
        damage_type=_damage_type(info),
        frontline=_clamp(frontline),
        difficulty=_difficulty(info.difficulty),
        **{k: _clamp(v) for k, v in base.items()},
    )
