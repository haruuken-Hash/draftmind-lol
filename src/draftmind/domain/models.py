"""Modelos de datos validados con Pydantic.

Pydantic comprueba tipos y rangos al crear cada objeto. Si el JSON de
demostración tuviera, por ejemplo, ``"engage": 7``, la carga fallaría con un
mensaje claro en lugar de producir análisis absurdos más tarde.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from draftmind.domain.enums import (
    ConfidenceLevel,
    DamageType,
    EvidenceKind,
    ExperienceLevel,
    ProfileOrigin,
    Role,
    SourceType,
    Verification,
)

# Escala común de los atributos cualitativos: 0 = nada, 3 = mucho.
Attr = Field(ge=0, le=3)


class DataSource(BaseModel):
    """De dónde viene un dato. Toda recomendación debe poder citarlo."""

    name: str
    kind: EvidenceKind
    url: str | None = None
    patch: str | None = None
    retrieved_at: datetime | None = None
    notes: str | None = None


class ChampionProfile(BaseModel):
    """Perfil cualitativo de un campeón (no son estadísticas)."""

    id: str
    origin: ProfileOrigin = ProfileOrigin.EDITORIAL
    # Si > 0, las posiciones salen de tantas apariciones en partidas reales
    # descargadas (match-v5), no de la clase del campeón.
    roles_observed: int = 0
    name: str
    roles: list[Role]
    damage_type: DamageType
    engage: int = Attr               # Capacidad de iniciar peleas.
    disengage: int = Attr            # Desenganche y protección de aliados.
    cc: int = Attr                   # Control de masas.
    early: int = Attr                # Presión en fase temprana.
    scaling: int = Attr              # Fuerza en fase tardía.
    frontline: int = Attr            # Aguante en primera línea.
    difficulty: int = Field(ge=1, le=3)
    resource_dependence: int = Attr  # Cuánto oro/experiencia necesita.


class ChampionInfo(BaseModel):
    """Datos estáticos de un campeón (Data Dragon). No incluye rendimiento."""

    id: str
    name: str
    key: int | None = None      # None si no viene de Data Dragon.
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    image_file: str | None = None
    # Valoraciones oficiales 0-10 de Data Dragon (None si no se conocen).
    attack: int | None = None
    defense: int | None = None
    magic: int | None = None
    difficulty: int | None = None
    attack_range: float | None = None


class AbilityInfo(BaseModel):
    key: str                    # "P" (pasiva), "Q", "W", "E" o "R".
    name: str
    description: str = ""
    cooldown: list[float] = Field(default_factory=list)
    image_path: str             # Ruta relativa en la caché de imágenes de Data Dragon.


class ChampionDetail(BaseModel):
    """Habilidades y consejos oficiales de un campeón (Data Dragon)."""

    id: str
    name: str
    title: str = ""
    lore: str = ""
    ally_tips: list[str] = Field(default_factory=list)    # Consejos para jugarlo.
    enemy_tips: list[str] = Field(default_factory=list)   # Consejos para jugar contra él.
    abilities: list[AbilityInfo] = Field(default_factory=list)


class ChampionCatalog(BaseModel):
    """Lista de campeones disponibles y de dónde salen."""

    source: DataSource
    version: str | None = None
    language: str | None = None
    champions: list[ChampionInfo]

    @property
    def from_data_dragon(self) -> bool:
        return self.version is not None


class ItemInfo(BaseModel):
    """Objeto de La Grieta del Invocador (dato estático oficial)."""

    id: str
    name: str
    plaintext: str = ""
    description: str = ""  # Texto sin etiquetas HTML.
    total_gold: int = 0
    tags: list[str] = Field(default_factory=list)
    image_file: str | None = None
    builds_from: list[str] = Field(default_factory=list)


class RuneInfo(BaseModel):
    id: int
    key: str
    name: str
    short_desc: str = ""
    icon: str = ""


class RunePathInfo(BaseModel):
    id: int
    key: str
    name: str
    icon: str = ""
    keystones: list[RuneInfo]
    minor_slots: list[list[RuneInfo]]


class SpellInfo(BaseModel):
    id: str
    key: int
    name: str
    description: str = ""
    cooldown: float | None = None
    image_file: str | None = None


class GameData(BaseModel):
    """Objetos, runas y hechizos de una versión de Data Dragon."""

    source: DataSource
    version: str
    language: str
    items: list[ItemInfo]          # Solo objetos completos de la Grieta.
    item_names: dict[str, str] = Field(default_factory=dict)  # Todos los ID -> nombre.
    rune_paths: list[RunePathInfo]
    spells: list[SpellInfo]

    def item_name(self, item_id: int | str) -> str:
        return self.item_names.get(str(item_id), f"Objeto #{item_id}")

    def item(self, item_id: int | str) -> ItemInfo | None:
        return next((i for i in self.items if i.id == str(item_id)), None)

    def spell(self, key: int) -> SpellInfo | None:
        return next((s for s in self.spells if s.key == key), None)

    def rune(self, rune_id: int) -> RuneInfo | None:
        for path in self.rune_paths:
            for rune in path.keystones + [r for slot in path.minor_slots for r in slot]:
                if rune.id == rune_id:
                    return rune
        return None


class MatchSummary(BaseModel):
    """Lo que interesa de una partida, desde el punto de vista de un jugador.

    Cualquier campo puede ser None si la fuente no lo incluye: así no se
    calculan métricas a partir de datos inexistentes.
    """

    match_id: str
    platform: str
    puuid: str
    is_demo: bool = False
    queue_id: int | None = None
    played_at: datetime | None = None
    duration_s: int | None = None
    patch: str | None = None
    champion_id: str
    role: Role | None = None
    win: bool | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    cs: int | None = None
    gold: int | None = None
    vision_score: int | None = None
    damage_to_champions: int | None = None
    damage_taken: int | None = None
    team_kills: int | None = None
    items: list[int] = Field(default_factory=list)
    summoner_spells: list[int] = Field(default_factory=list)
    keystone_id: int | None = None
    allies: list[str] = Field(default_factory=list)
    enemies: list[str] = Field(default_factory=list)
    lane_opponent: str | None = None
    # Para enlazar con el timeline (participantId 1-10 de match-v5).
    participant_id: int | None = None
    opponent_participant_id: int | None = None
    # Puntuación de rendimiento comparada con los 10 jugadores (analysis/performance.py).
    performance_score: float | None = None
    performance_rank: int | None = None
    badge: str | None = None


class ChampionStat(BaseModel):
    """Estadística normalizada de cualquier proveedor.

    Solo ``champion_id``, ``games`` y ``source`` son obligatorios. Lo que la
    fuente no ofrece queda en None: nunca se rellena con valores inventados.
    """

    champion_id: str
    games: int = Field(ge=0)
    source: DataSource
    role: Role | None = None
    opponent_id: str | None = None   # Solo en estadísticas de enfrentamiento.
    patch: str | None = None
    region: str | None = None
    rank_segment: str | None = None
    wins: int | None = None
    win_rate: float | None = Field(default=None, ge=0, le=1)
    pick_rate: float | None = Field(default=None, ge=0, le=1)
    ban_rate: float | None = Field(default=None, ge=0, le=1)

    @property
    def observed_win_rate(self) -> float | None:
        if self.win_rate is not None:
            return self.win_rate
        if self.wins is not None and self.games:
            return self.wins / self.games
        return None


class RankedEntry(BaseModel):
    """league-v4: una cola clasificatoria del jugador."""

    queue: str           # RANKED_SOLO_5x5, RANKED_FLEX_SR...
    tier: str            # IRON ... CHALLENGER
    division: str        # I-IV (vacío en Maestro o superior)
    lp: int
    wins: int
    losses: int
    hot_streak: bool = False

    @property
    def queue_label(self) -> str:
        return {"RANKED_SOLO_5x5": "Clasificatoria Solo/Dúo", "RANKED_FLEX_SR": "Clasificatoria Flexible"}.get(
            self.queue, self.queue)

    @property
    def tier_label(self) -> str:
        names = {"IRON": "Hierro", "BRONZE": "Bronce", "SILVER": "Plata", "GOLD": "Oro", "PLATINUM": "Platino",
                 "EMERALD": "Esmeralda", "DIAMOND": "Diamante", "MASTER": "Maestro",
                 "GRANDMASTER": "Gran Maestro", "CHALLENGER": "Retador"}
        name = names.get(self.tier, self.tier.title())
        return f"{name} {self.division}" if self.tier not in ("MASTER", "GRANDMASTER", "CHALLENGER") else name

    @property
    def win_rate(self) -> float | None:
        total = self.wins + self.losses
        return self.wins / total if total else None


class MasteryEntry(BaseModel):
    champion_key: int    # Número de campeón (champion.json «key»).
    level: int
    points: int
    last_played: datetime | None = None


class PlayerProfile(BaseModel):
    ranked: list[RankedEntry] = Field(default_factory=list)
    masteries: list[MasteryEntry] = Field(default_factory=list)
    retrieved_at: datetime


class Observation(BaseModel):
    """Observación educativa sobre el rendimiento, con su base de datos."""

    kind: EvidenceKind
    text: str
    sample_size: int | None = None


class ResearchSource(BaseModel):
    """Fuente consultada por el usuario. No se considera un hecho verificado
    hasta que se contrasta con otra fuente."""

    id: int | None = None
    url: str
    title: str
    source_type: SourceType
    published_on: str = ""           # Texto libre: no siempre se conoce.
    retrieved_at: datetime
    patch: str = ""
    claim: str = ""                  # Afirmación concreta que respalda.
    verification: Verification = Verification.UNVERIFIED
    notes: str = ""


class DemoDataset(BaseModel):
    source: DataSource
    champions: list[ChampionProfile]


class DraftPick(BaseModel):
    champion_id: str
    role: Role | None = None  # None = rol desconocido.


class DraftState(BaseModel):
    """Lo que el usuario ha introducido manualmente en la pantalla de draft."""

    my_role: Role | None = None
    my_champion_id: str | None = None  # None = todavía sin decidir.
    allies: list[DraftPick] = Field(default_factory=list)
    enemies: list[DraftPick] = Field(default_factory=list)
    bans: list[str] = Field(default_factory=list)  # Campeones bloqueados: no se sugieren.


class UserProfile(BaseModel):
    favorite_champions: list[str] = Field(default_factory=list)
    main_roles: list[Role] = Field(default_factory=list)
    experience: ExperienceLevel = ExperienceLevel.UNSET
    learning_goals: str = ""


class FactorResult(BaseModel):
    """Contribución de un criterio al análisis de un candidato.

    ``score`` va de -2 (muy desfavorable) a +2 (muy favorable). ``weight``
    indica cuánto pesa este criterio en la puntuación total.
    """

    key: str
    label: str
    score: float = Field(ge=-2, le=2)
    weight: float = 1.0
    explanation: str
    kind: EvidenceKind


class ConfidenceAssessment(BaseModel):
    level: ConfidenceLevel
    reasons: list[str]
    warnings: list[str] = Field(default_factory=list)


class TeamProfile(BaseModel):
    """Resumen agregado de una composición (aliada o enemiga)."""

    champion_ids: list[str]
    physical_share: float = 0.0  # Proporción de daño físico (0-1).
    magic_share: float = 0.0
    engage: int = 0
    disengage: int = 0
    cc: int = 0
    early: int = 0
    scaling: int = 0
    frontline: int = 0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class CandidateAnalysis(BaseModel):
    champion: ChampionProfile
    score: float  # 0-100, solo orientativo para comparar candidatos.
    factors: list[FactorResult]
    pros: list[str]
    cons: list[str]
    confidence: ConfidenceAssessment
    sources: list[DataSource]
