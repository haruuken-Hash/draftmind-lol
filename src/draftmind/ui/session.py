"""Estado compartido entre pantallas.

El draft que el usuario monta en «Draft» lo leen «Estrategia» y «Runas y
builds»; las partidas cargadas en «Historial» las usan «Análisis
postpartida» y las estadísticas personales. Las vistas se suscriben a las
señales en vez de conocerse entre sí.
"""

from PySide6.QtCore import QObject, Signal

from draftmind.data.repositories.match_repository import LinkedAccount
from draftmind.domain.models import DraftState, MatchSummary


class AppSession(QObject):
    draft_changed = Signal()
    matches_changed = Signal()
    filter_changed = Signal()
    match_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.draft = DraftState()
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

    def match(self, match_id: str) -> MatchSummary | None:
        return next((m for m in self.matches if m.match_id == match_id), None)
