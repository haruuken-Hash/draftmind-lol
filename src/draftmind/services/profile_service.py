"""Combina las fuentes de perfiles cualitativos.

Prioridad (la siguiente sustituye a la anterior para el mismo campeón):
1. Estimación automática a partir de Data Dragon (todos los campeones; en la
   práctica, solo cuenta para los que salgan después del perfil editorial).
   Sus POSICIONES se corrigen con las observadas en partidas reales
   descargadas, si hay datos suficientes.
2. Perfil editorial (los 173 campeones de 16.21.1, escritos a mano).
3. Perfil revisado por el usuario en la app.
"""

from collections import Counter
from collections.abc import Iterable

from draftmind.analysis.profile_estimator import can_estimate, estimate_profile
from draftmind.domain.enums import ProfileOrigin, Role
from draftmind.domain.models import ChampionCatalog, ChampionProfile

# Una posición se acepta si aparece al menos MIN_OBSERVATIONS veces y supone
# al menos MIN_SHARE de las apariciones de ese campeón.
MIN_OBSERVATIONS = 2
MIN_SHARE = 0.25
MIN_GAME_SECONDS = 300  # Las partidas más cortas (posibles remakes) no cuentan.


def observed_positions(raw_matches: Iterable[dict]) -> dict[str, Counter]:
    """Posiciones de los 10 jugadores de cada partida (championName + teamPosition)."""
    positions: dict[str, Counter] = {}
    for raw in raw_matches:
        info = raw.get("info") or {}
        duration = info.get("gameDuration")
        if isinstance(duration, int) and "gameEndTimestamp" not in info:
            duration //= 1000  # Formato anterior al parche 11.20.
        if not isinstance(duration, int) or duration < MIN_GAME_SECONDS:
            continue
        for player in info.get("participants") or []:
            champion, position = player.get("championName"), player.get("teamPosition")
            try:
                role = Role(position)
            except ValueError:
                continue  # Posición vacía o desconocida.
            if champion:
                positions.setdefault(champion, Counter())[role] += 1
    return positions


def _observed_roles(counts: Counter) -> list[Role]:
    total = sum(counts.values())
    return [role for role, n in counts.most_common()
            if n >= MIN_OBSERVATIONS and n / total >= MIN_SHARE]


def build_profiles(
    catalog: ChampionCatalog,
    editorial: list[ChampionProfile],
    overrides: list[ChampionProfile],
    positions: dict[str, Counter] | None = None,
) -> list[ChampionProfile]:
    positions = positions or {}
    profiles: dict[str, ChampionProfile] = {}
    for info in catalog.champions:
        if not can_estimate(info):
            continue
        profile = estimate_profile(info)
        counts = positions.get(info.id)
        roles = _observed_roles(counts) if counts else []
        if roles:
            profile = profile.model_copy(update={"roles": roles, "roles_observed": sum(counts.values())})
        profiles[info.id] = profile
    for p in editorial:
        profiles[p.id] = p.model_copy(update={"origin": ProfileOrigin.EDITORIAL})
    for p in overrides:
        profiles[p.id] = p.model_copy(update={"origin": ProfileOrigin.USER})
    return sorted(profiles.values(), key=lambda p: p.name)
