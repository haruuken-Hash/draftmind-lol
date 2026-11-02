"""Combina las tres fuentes de perfiles cualitativos.

Prioridad (la siguiente sustituye a la anterior para el mismo campeón):
1. Estimación automática a partir de Data Dragon (todos los campeones).
2. Perfil editorial de demostración (26 campeones escritos a mano).
3. Perfil revisado por el usuario en la app.
"""

from draftmind.analysis.profile_estimator import can_estimate, estimate_profile
from draftmind.domain.enums import ProfileOrigin
from draftmind.domain.models import ChampionCatalog, ChampionProfile


def build_profiles(
    catalog: ChampionCatalog,
    editorial: list[ChampionProfile],
    overrides: list[ChampionProfile],
) -> list[ChampionProfile]:
    profiles: dict[str, ChampionProfile] = {}
    for info in catalog.champions:
        if can_estimate(info):
            profiles[info.id] = estimate_profile(info)
    for p in editorial:
        profiles[p.id] = p.model_copy(update={"origin": ProfileOrigin.EDITORIAL})
    for p in overrides:
        profiles[p.id] = p.model_copy(update={"origin": ProfileOrigin.USER})
    return sorted(profiles.values(), key=lambda p: p.name)
