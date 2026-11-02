"""Estado compartido entre pantallas.

El draft que el usuario monta en «Draft» lo leen «Estrategia» y «Runas y
builds»; las partidas cargadas en «Historial» las usan «Análisis
postpartida» y las estadísticas personales. Las vistas se suscriben a las
señales en vez de conocerse entre sí.
"""

from PySide6.QtCore import QObject, Signal

from draftmind.data.repositories.match_repository import LinkedAccount
from draftmind.domain.models import DraftState, MatchSummary, PlayerProfile


class AppSession(QObject):
    draft_changed = Signal()
    matches_changed = Signal()
    filter_changed = Signal()
    match_selected = Signal(str)
    player_profile_changed = Signal()

    def __init__(self):
        super().__init__()
        self.draft = DraftState()
        self.player_profile: PlayerProfile | None = None  # Rango y maestría (Riot API).
        self.account: LinkedAccount | None = None
        self.matches: list[MatchSummary] = []
        self.filtered: list[MatchSummary] = []
        self.matches_are_demo = False

    def set_draft(self, draft: DraftState) -> None:
        self.draft = draft
        self.draft_changed.emit()

    def set_matches(self, account: LinkedAccount | None, matches: list[MatchSummary], demo: bool) -> None:
        self.account = account
        self.matches = matches
        self.filtered = list(matches)
        self.matches_are_demo = demo
        self.matches_changed.emit()

    def set_filtered(self, matches: list[MatchSummary]) -> None:
        self.filtered = matches
        self.filter_changed.emit()

    def set_player_profile(self, profile: PlayerProfile | None) -> None:
        self.player_profile = profile
        self.player_profile_changed.emit()

    def mastery_champion_keys(self) -> list[int]:
        return [m.champion_key for m in self.player_profile.masteries] if self.player_profile else []

    def match(self, match_id: str) -> MatchSummary | None:
        return next((m for m in self.matches if m.match_id == match_id), None)
