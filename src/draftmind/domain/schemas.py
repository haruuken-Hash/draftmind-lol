"""Esquemas de datos EXTERNOS (respuestas de Data Dragon).

Se separan de ``models.py`` porque describen el formato de otra empresa, que
puede cambiar. Solo se declaran los campos que usamos; Pydantic ignora el
resto. Formato comprobado con champion.json de la versión 16.21.1.
"""

from pydantic import BaseModel, Field


class DDragonImage(BaseModel):
    full: str  # Nombre del archivo, p. ej. "MonkeyKing.png".


class DDragonInfo(BaseModel):
    """Valoraciones oficiales de 0 a 10 que muestra el propio juego."""

    attack: int = 0
    defense: int = 0
    magic: int = 0
    difficulty: int = 0


class DDragonStats(BaseModel):
    """Estadísticas base. ``attackdamageperlevel`` no se lee: en 16.21.1 vale 0
    para los 173 campeones, así que ese dato de Data Dragon no es fiable."""

    attackrange: float = 0
    hp: float = 0
    hpperlevel: float = 0
    armor: float = 0
    armorperlevel: float = 0
    spellblock: float = 0
    spellblockperlevel: float = 0
    attackdamage: float = 0
    attackspeed: float = 0
    movespeed: float = 0


class DDragonChampion(BaseModel):
    id: str           # Identificador interno, p. ej. "MonkeyKing".
    key: int          # Número de campeón (llega como texto: "62").
    name: str         # Nombre traducido, p. ej. "Wukong".
    title: str
    tags: list[str]   # Clases oficiales: Fighter, Tank, Mage, Assassin, Marksman, Support.
    image: DDragonImage
    info: DDragonInfo = Field(default_factory=DDragonInfo)
    stats: DDragonStats = Field(default_factory=DDragonStats)


class DDragonChampionFile(BaseModel):
    type: str
    version: str
    data: dict[str, DDragonChampion]


# --- champion/{id}.json: detalle de un campeón (comprobado con 16.21.1) ----------

class DDragonAbility(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    cooldown: list[float] = Field(default_factory=list)
    image: DDragonImage


class DDragonChampionDetail(BaseModel):
    id: str
    name: str
    title: str = ""
    lore: str = ""
    allytips: list[str] = Field(default_factory=list)
    enemytips: list[str] = Field(default_factory=list)
    passive: DDragonAbility
    spells: list[DDragonAbility] = Field(default_factory=list)


class DDragonChampionDetailFile(BaseModel):
    data: dict[str, DDragonChampionDetail]


# --- item.json (comprobado con 16.21.1) ---------------------------------------

class DDragonGold(BaseModel):
    base: int = 0
    total: int = 0
    sell: int = 0
    purchasable: bool = False


class DDragonItem(BaseModel):
    name: str
    description: str = ""
    plaintext: str = ""
    gold: DDragonGold = Field(default_factory=DDragonGold)
    tags: list[str] = Field(default_factory=list)
    maps: dict[str, bool] = Field(default_factory=dict)  # "11" = La Grieta del Invocador.
    into: list[str] = Field(default_factory=list)
    from_: list[str] = Field(default_factory=list, alias="from")
    image: DDragonImage
    inStore: bool | None = None
    requiredChampion: str | None = None


class DDragonItemFile(BaseModel):
    type: str
    version: str
    data: dict[str, DDragonItem]


# --- runesReforged.json (lista de árboles) -----------------------------------

class DDragonRune(BaseModel):
    id: int
    key: str
    icon: str
    name: str
    shortDesc: str = ""
    longDesc: str = ""


class DDragonRuneSlot(BaseModel):
    runes: list[DDragonRune]


class DDragonRunePath(BaseModel):
    id: int
    key: str
    icon: str
    name: str
    slots: list[DDragonRuneSlot]


# --- summoner.json -------------------------------------------------------------

class DDragonSpell(BaseModel):
    id: str
    key: int
    name: str
    description: str = ""
    cooldown: list[float] = Field(default_factory=list)
    summonerLevel: int = 0
    modes: list[str] = Field(default_factory=list)
    image: DDragonImage


class DDragonSpellFile(BaseModel):
    type: str
    version: str
    data: dict[str, DDragonSpell]
