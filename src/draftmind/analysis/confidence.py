"""Criterios de confianza de una recomendación.

Los umbrales son deliberadamente conservadores y están documentados en
docs/architecture.md. La confianza depende de los DATOS, nunca de lo
convincente que suene una explicación.

Reglas:
1. Sin datos                                   -> insuficiente.
2. Solo datos cualitativos/editoriales          -> baja (como máximo).
3. Datos estadísticos según tamaño de muestra:
      < 100 partidas                            -> insuficiente
      100 - 999                                 -> baja
      1000 - 4999                               -> media
      >= 5000                                   -> alta
4. Parche distinto al actual o datos con más de STALE_AFTER_DAYS días:
   se baja un nivel y se añade una advertencia visible.
"""

from draftmind.domain.enums import ConfidenceLevel
from draftmind.domain.models import ConfidenceAssessment

MIN_SAMPLE = 100
MEDIUM_SAMPLE = 1000
HIGH_SAMPLE = 5000
STALE_AFTER_DAYS = 14

_ORDER = [
    ConfidenceLevel.INSUFFICIENT,
    ConfidenceLevel.LOW,
    ConfidenceLevel.MEDIUM,
    ConfidenceLevel.HIGH,
]


def _downgrade(level: ConfidenceLevel) -> ConfidenceLevel:
    return _ORDER[max(0, _ORDER.index(level) - 1)]


def assess_confidence(
    *,
    has_data: bool,
    is_statistical: bool,
    sample_size: int | None = None,
    same_patch: bool | None = None,
    data_age_days: float | None = None,
) -> ConfidenceAssessment:
    if not has_data:
        return ConfidenceAssessment(
            level=ConfidenceLevel.INSUFFICIENT,
            reasons=["No hay datos disponibles para este análisis."],
        )

    if not is_statistical:
        return ConfidenceAssessment(
            level=ConfidenceLevel.LOW,
            reasons=[
                "El análisis se basa solo en perfiles cualitativos, no en estadísticas de partidas.",
            ],
        )

    reasons: list[str] = []
    warnings: list[str] = []

    if sample_size is None:
        level = ConfidenceLevel.LOW
        reasons.append("La fuente no indica el tamaño de muestra.")
    elif sample_size < MIN_SAMPLE:
        return ConfidenceAssessment(
            level=ConfidenceLevel.INSUFFICIENT,
            reasons=[f"Muestra demasiado pequeña ({sample_size} partidas; mínimo {MIN_SAMPLE})."],
        )
    elif sample_size < MEDIUM_SAMPLE:
        level = ConfidenceLevel.LOW
        reasons.append(f"Muestra reducida ({sample_size} partidas).")
    elif sample_size < HIGH_SAMPLE:
        level = ConfidenceLevel.MEDIUM
        reasons.append(f"Muestra moderada ({sample_size} partidas).")
    else:
        level = ConfidenceLevel.HIGH
        reasons.append(f"Muestra amplia ({sample_size} partidas).")

    if same_patch is False:
        level = _downgrade(level)
        warnings.append("Los datos pertenecen a un parche distinto del actual.")
    if data_age_days is not None and data_age_days > STALE_AFTER_DAYS:
        level = _downgrade(level)
        warnings.append(f"Los datos tienen {int(data_age_days)} días; pueden estar desactualizados.")

    return ConfidenceAssessment(level=level, reasons=reasons, warnings=warnings)
