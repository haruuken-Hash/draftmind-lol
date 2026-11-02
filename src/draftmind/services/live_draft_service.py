"""Seguimiento del cliente de LoL para el draft en vivo.

Cada llamada a ``poll()`` hace como mucho dos peticiones GET locales y
devuelve un estado. La interfaz lo llama periódicamente en segundo plano.

Durante la partida (fases InProgress, GameStart, Reconnect) no se lee ni se
analiza nada: la política de Riot no permite que una aplicación saque
conclusiones por el jugador mientras juega.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from draftmind.integrations.champ_select import LiveDraft, parse_session
from draftmind.integrations.league_client import (
    LeagueClient,
    LeagueClientError,
    Lockfile,
    read_lockfile,
)

IN_GAME_PHASES = {"GameStart", "InProgress", "Reconnect"}
PHASE_LABELS = {
    "None": "en el menú principal",
    "Lobby": "en una sala",
    "Matchmaking": "buscando partida",
    "ReadyCheck": "aceptando partida",
    "ChampSelect": "en selección de campeones",
    "WaitingForStats": "esperando estadísticas",
    "PreEndOfGame": "fin de partida",
    "EndOfGame": "fin de partida",
}


class LiveState(str, Enum):
    NO_CLIENT = "sin_cliente"
    CLIENT_IDLE = "cliente_abierto"
    CHAMP_SELECT = "seleccion"
    IN_GAME = "en_partida"
    ERROR = "error"


@dataclass
class LiveStatus:
    state: LiveState
    message: str
    draft: LiveDraft | None = None
    certificate_verified: bool = True


class LiveDraftService:
    def __init__(
        self,
        install_dir: Path,
        key_to_id: Callable[[], dict[int, str]],
        lockfile_reader: Callable[[Path], Lockfile | None] = read_lockfile,
        client_factory: Callable[[Lockfile], LeagueClient] = LeagueClient,
    ):
        self.install_dir = install_dir
        self._key_to_id = key_to_id
        self._read_lockfile = lockfile_reader
        self._client_factory = client_factory
        self._client: LeagueClient | None = None
        self._lockfile: Lockfile | None = None

    def poll(self) -> LiveStatus:
        try:
            lockfile = self._read_lockfile(self.install_dir)
        except LeagueClientError as exc:
            return LiveStatus(LiveState.ERROR, str(exc))
        if lockfile is None:
            self._client = None
            return LiveStatus(LiveState.NO_CLIENT, "El cliente de LoL no está abierto.")
        if self._client is None or lockfile != self._lockfile:
            self._client = self._client_factory(lockfile)
            self._lockfile = lockfile

        try:
            phase = self._client.gameflow_phase()
            verified = getattr(self._client, "certificate_verified", True)
            if phase in IN_GAME_PHASES:
                return LiveStatus(
                    LiveState.IN_GAME,
                    "Partida en curso: el asistente no se actualiza ni da indicaciones durante la partida.",
                    certificate_verified=verified,
                )
            if phase != "ChampSelect":
                label = PHASE_LABELS.get(phase, phase)
                return LiveStatus(LiveState.CLIENT_IDLE, f"Cliente abierto, {label}.", certificate_verified=verified)
            session = self._client.champ_select_session()
        except LeagueClientError as exc:
            return LiveStatus(LiveState.ERROR, str(exc))

        if session is None:
            return LiveStatus(LiveState.CLIENT_IDLE, "Cliente abierto, sin selección de campeones activa.")
        key_to_id = self._key_to_id()
        if not key_to_id:
            return LiveStatus(LiveState.ERROR, "Hacen falta los datos de Data Dragon para reconocer los campeones.")
        draft = parse_session(session, key_to_id)
        message = "Selección de campeones en curso."
        if draft.unknown_champion_keys:
            message += " Algún campeón no aparece en Data Dragon todavía (¿datos de otro parche?)."
        return LiveStatus(LiveState.CHAMP_SELECT, message, draft, certificate_verified=verified)
