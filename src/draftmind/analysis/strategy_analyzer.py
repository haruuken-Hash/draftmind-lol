"""Análisis estratégico educativo de dos composiciones.

Separa:
- HECHOS DEL DRAFT: lo que se deduce directamente de los campeones elegidos y
  sus perfiles (sumas, reparto de daño).
- HIPÓTESIS: condiciones de victoria, ventanas de poder y riesgos. Son
  inferencias para reflexionar, no instrucciones.
Solo usa lo que el usuario introduce; no usa información oculta del rival.
"""

from pydantic import BaseModel

from draftmind.analysis.composition_analyzer import HIGH_DISENGAGE, HIGH_ENGAGE, LOW_FRONTLINE
from draftmind.domain.models import TeamProfile

MIN_CHAMPIONS = 3


class TeamStrategy(BaseModel):
    facts: list[str]
    win_conditions: list[str]
    risks: list[str]


class StrategyReport(BaseModel):
    ally: TeamStrategy
    enemy: TeamStrategy
    power_window: str
    objectives: str
    questions: list[str]
    enough_data: bool


def _facts(team: TeamProfile) -> list[str]:
    if not team.champion_ids:
        return ["Sin campeones con perfil."]
    n = len(team.champion_ids)
    return [
        f"{n} campeones con perfil.",
        f"Reparto de daño: {team.physical_share:.0%} físico, {team.magic_share:.0%} mágico.",
        f"Suma de iniciación {team.engage}, desenganche {team.disengage}, control {team.cc}, "
        f"primera línea {team.frontline}.",
        f"Presión temprana {team.early} frente a escalado {team.scaling}.",
    ]


def _team_strategy(team: TeamProfile, other: TeamProfile) -> TeamStrategy:
    wins, risks = [], []
    if team.champion_ids:
        if team.early > team.scaling + 2:
            wins.append("Conseguir ventaja pronto: presionar objetivos neutrales tempranos y forzar peleas "
                        "antes de que el rival complete sus objetos.")
        elif team.scaling > team.early + 2:
            wins.append("Llegar a la fase tardía en igualdad: priorizar farmeo y visión y aceptar peleas "
                        "cuando los objetos clave estén completos.")
        if team.engage >= HIGH_ENGAGE:
            wins.append("Buscar peleas iniciadas por el equipo, idealmente cuando el rival esté separado o "
                        "en zonas estrechas.")
            if other.champion_ids and other.frontline < LOW_FRONTLINE:
                wins.append("El rival tiene poca primera línea: una buena iniciación puede alcanzar a sus "
                            "objetivos frágiles.")
        if team.disengage >= HIGH_DISENGAGE:
            wins.append("Jugar a contraatacar: dejar que el rival inicie y castigar su entrada con "
                        "desenganche y protección.")
        if not wins:
            wins.append("Sin una condición de victoria clara en los perfiles: el plan depende más de la "
                        "ejecución y de cómo evolucione la partida.")
        if len(team.champion_ids) >= MIN_CHAMPIONS:
            risks += team.weaknesses
            if team.engage < 3 and team.disengage < 3:
                risks.append("Ni mucha iniciación ni mucho desenganche: puede costar decidir cuándo pelear.")
    return TeamStrategy(facts=_facts(team), win_conditions=wins, risks=risks)


def analyze_strategy(ally: TeamProfile, enemy: TeamProfile) -> StrategyReport:
    enough = len(ally.champion_ids) >= MIN_CHAMPIONS and len(enemy.champion_ids) >= MIN_CHAMPIONS

    if not ally.champion_ids or not enemy.champion_ids:
        window = "Hacen falta campeones con perfil en ambos equipos para comparar ventanas de poder."
    else:
        ally_bias = ally.early / len(ally.champion_ids) - ally.scaling / len(ally.champion_ids)
        enemy_bias = enemy.early / len(enemy.champion_ids) - enemy.scaling / len(enemy.champion_ids)
        if ally_bias - enemy_bias >= 0.5:
            window = ("Hipótesis: tu equipo es relativamente más fuerte al principio; el rival tenderá a "
                      "mejorar con el tiempo.")
        elif enemy_bias - ally_bias >= 0.5:
            window = ("Hipótesis: el rival es relativamente más fuerte al principio; tu equipo tenderá a "
                      "mejorar con el tiempo.")
        else:
            window = "Hipótesis: ventanas de poder parecidas; no hay una fase claramente favorable."

    if ally.champion_ids and enemy.champion_ids:
        ally_pressure, enemy_pressure = ally.early + ally.engage, enemy.early + enemy.engage
        if ally_pressure > enemy_pressure + 2:
            objectives = "Hipótesis: tu equipo tiene más potencial de presión sobre objetivos neutrales."
        elif enemy_pressure > ally_pressure + 2:
            objectives = ("Hipótesis: el rival tiene más potencial de presión sobre objetivos; la visión "
                          "previa y no pelear en desventaja numérica cobran importancia.")
        else:
            objectives = "Hipótesis: potencial de presión sobre objetivos parecido en ambos equipos."
    else:
        objectives = "Sin datos suficientes para comparar la presión sobre objetivos."

    questions = [
        "¿En qué fase de la partida es más fuerte mi equipo y la estamos aprovechando?",
        "¿Quién del rival puede iniciar las peleas y dónde está ahora?",
        "Antes de un objetivo: ¿tenemos visión y estamos en igualdad numérica?",
        "¿Mi papel en las peleas es iniciar, proteger o hacer daño? ¿Mi posición lo permite?",
    ]
    if ally.scaling > ally.early + 2:
        questions.append("¿Estoy aceptando peleas que no necesito antes de tener mis objetos?")
    if enemy.engage >= HIGH_ENGAGE:
        questions.append("¿Estoy en una posición en la que su iniciación pueda alcanzarme?")

    return StrategyReport(
        ally=_team_strategy(ally, enemy),
        enemy=_team_strategy(enemy, ally),
        power_window=window,
        objectives=objectives,
        questions=questions,
        enough_data=enough,
    )
