"""Análisis de una composición a partir de perfiles cualitativos.

Todas las conclusiones de este módulo son INFERENCIAS: describen tendencias
probables de una composición, no resultados garantizados.
"""

from collections.abc import Iterable

from draftmind.domain.enums import DamageType
from draftmind.domain.models import ChampionProfile, TeamProfile

# Umbrales (sobre la suma de atributos 0-3 del equipo).
LOW_FRONTLINE = 3
LOW_ENGAGE = 3
HIGH_ENGAGE = 6
HIGH_DISENGAGE = 5
HIGH_CC = 8
DAMAGE_CONCENTRATION = 0.8  # >= 80 % de un tipo de daño.
MIN_CHAMPS_FOR_GAPS = 3     # Con menos campeones no se señalan carencias.


def damage_shares(champions: Iterable[ChampionProfile]) -> tuple[float, float]:
    """Proporción de daño (físico, mágico). Los mixtos cuentan mitad y mitad."""
    physical = magic = 0.0
    for c in champions:
        if c.damage_type is DamageType.PHYSICAL:
            physical += 1
        elif c.damage_type is DamageType.MAGIC:
            magic += 1
        else:
            physical += 0.5
            magic += 0.5
    total = physical + magic
    if total == 0:
        return 0.0, 0.0
    return physical / total, magic / total


def analyze_team(champions: list[ChampionProfile]) -> TeamProfile:
    physical, magic = damage_shares(champions)
    team = TeamProfile(
        champion_ids=[c.id for c in champions],
        physical_share=physical,
        magic_share=magic,
        engage=sum(c.engage for c in champions),
        disengage=sum(c.disengage for c in champions),
        cc=sum(c.cc for c in champions),
        early=sum(c.early for c in champions),
        scaling=sum(c.scaling for c in champions),
        frontline=sum(c.frontline for c in champions),
    )
    if not champions:
        return team

    if team.engage >= HIGH_ENGAGE:
        team.strengths.append("Buena capacidad para iniciar peleas.")
    if team.disengage >= HIGH_DISENGAGE:
        team.strengths.append("Buenas herramientas de desenganche y protección.")
    if team.cc >= HIGH_CC:
        team.strengths.append("Abundante control de masas.")
    if team.early > team.scaling + 2:
        team.strengths.append("Orientada a la presión temprana: le conviene forzar acción pronto.")
    elif team.scaling > team.early + 2:
        team.strengths.append("Orientada al escalado: tiende a mejorar con el tiempo.")

    if len(champions) >= MIN_CHAMPS_FOR_GAPS:
        if team.frontline < LOW_FRONTLINE:
            team.weaknesses.append("Poca primera línea: puede costar aguantar el daño en peleas frontales.")
        if team.engage < LOW_ENGAGE:
            team.weaknesses.append("Poca iniciación: puede depender de que el rival cometa errores.")
        if physical >= DAMAGE_CONCENTRATION:
            team.weaknesses.append("Daño casi todo físico: el rival puede priorizar armadura.")
        elif magic >= DAMAGE_CONCENTRATION:
            team.weaknesses.append("Daño casi todo mágico: el rival puede priorizar resistencia mágica.")
    return team
