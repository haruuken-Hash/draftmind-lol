"""Enumeraciones compartidas por toda la aplicación.

Los valores internos (en inglés y mayúsculas) coinciden con los que usa la
API de Riot para las posiciones (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY), de
modo que más adelante no haga falta traducir entre dos vocabularios.
La propiedad ``label`` devuelve el texto que se muestra al usuario.
"""

from enum import Enum


class Role(str, Enum):
    TOP = "TOP"
    JUNGLE = "JUNGLE"
    MIDDLE = "MIDDLE"
    BOTTOM = "BOTTOM"
    UTILITY = "UTILITY"

    @property
    def label(self) -> str:
        return {
            Role.TOP: "Superior",
            Role.JUNGLE: "Jungla",
            Role.MIDDLE: "Medio",
            Role.BOTTOM: "Tirador",
            Role.UTILITY: "Soporte",
        }[self]


class DamageType(str, Enum):
    PHYSICAL = "PHYSICAL"
    MAGIC = "MAGIC"
    MIXED = "MIXED"

    @property
    def label(self) -> str:
        return {
            DamageType.PHYSICAL: "Físico",
            DamageType.MAGIC: "Mágico",
            DamageType.MIXED: "Mixto",
        }[self]


class EvidenceKind(str, Enum):
    """Tipo de afirmación. Sirve para no mezclar hechos con opiniones."""

    OFFICIAL = "oficial"          # Dato estático oficial (nombres, clases...).
    OBSERVED = "observado"        # Dato estadístico medido en una fuente.
    INFERENCE = "inferencia"      # Razonamiento estratégico a partir de datos.
    EDUCATIONAL = "educativo"     # Sugerencia general o dato editorial.
    INSUFFICIENT = "insuficiente" # No hay datos para afirmar nada.

    @property
    def label(self) -> str:
        return {
            EvidenceKind.OFFICIAL: "Dato oficial",
            EvidenceKind.OBSERVED: "Estadística observada",
            EvidenceKind.INFERENCE: "Inferencia estratégica",
            EvidenceKind.EDUCATIONAL: "Sugerencia educativa",
            EvidenceKind.INSUFFICIENT: "Evidencia insuficiente",
        }[self]


class ConfidenceLevel(str, Enum):
    HIGH = "alta"
    MEDIUM = "media"
    LOW = "baja"
    INSUFFICIENT = "insuficiente"

    @property
    def label(self) -> str:
        return {
            ConfidenceLevel.HIGH: "Alta",
            ConfidenceLevel.MEDIUM: "Media",
            ConfidenceLevel.LOW: "Baja",
            ConfidenceLevel.INSUFFICIENT: "Insuficiente",
        }[self]


class ProfileOrigin(str, Enum):
    """De dónde sale el perfil cualitativo de un campeón (de menos a más fiable)."""

    ESTIMATED = "estimado"     # Calculado con reglas a partir de Data Dragon.
    EDITORIAL = "editorial"    # Escrito a mano en los datos de demostración.
    USER = "usuario"           # Revisado por el propio usuario en la app.

    @property
    def label(self) -> str:
        return {
            ProfileOrigin.ESTIMATED: "Estimación automática",
            ProfileOrigin.EDITORIAL: "Perfil editorial de demostración",
            ProfileOrigin.USER: "Revisado por ti",
        }[self]


class SourceType(str, Enum):
    """Tipo de fuente de investigación: separa las primarias de las opiniones."""

    OFFICIAL = "oficial"
    DATA = "datos"
    ANALYSIS = "analisis"
    COMMUNITY = "comunidad"

    @property
    def label(self) -> str:
        return {
            SourceType.OFFICIAL: "Oficial (fuente primaria)",
            SourceType.DATA: "Datos o estadísticas",
            SourceType.ANALYSIS: "Análisis u opinión",
            SourceType.COMMUNITY: "Comunidad (foros, vídeos)",
        }[self]


class Verification(str, Enum):
    UNVERIFIED = "sin_verificar"
    CONFIRMED = "contrastada"
    DISPUTED = "contradicha"

    @property
    def label(self) -> str:
        return {
            Verification.UNVERIFIED: "Sin verificar",
            Verification.CONFIRMED: "Contrastada con otra fuente",
            Verification.DISPUTED: "Contradicha por otra fuente",
        }[self]


class ExperienceLevel(str, Enum):
    UNSET = "sin_definir"
    BEGINNER = "principiante"
    INTERMEDIATE = "intermedio"
    ADVANCED = "avanzado"

    @property
    def label(self) -> str:
        return {
            ExperienceLevel.UNSET: "Sin definir",
            ExperienceLevel.BEGINNER: "Principiante",
            ExperienceLevel.INTERMEDIATE: "Intermedio",
            ExperienceLevel.ADVANCED: "Avanzado",
        }[self]
