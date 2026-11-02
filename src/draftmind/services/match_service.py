"""Partidas del usuario: Riot API (con caché en SQLite) o demostración.

Peticiones por carga: 1 de cuenta (solo la primera vez; el PUUID se guarda),
1 de lista de partidas y 1 por cada partida que no esté ya guardada. El
número de partidas está limitado (MAX_MATCHES) para no consultar todo el
historial innecesariamente.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from draftmind.analysis.lane_analyzer import LaneAnalysis, analyze_lane, players_from_match
from draftmind.data.repositories.match_repository import LinkedAccount, MatchRepository
from draftmind.domain.models import MasteryEntry, MatchSummary, PlayerProfile, RankedEntry
from draftmind.integrations.riot_api import Platform, RiotApiClient
from draftmind.integrations.riot_match import summarize_match

log = logging.getLogger(__name__)

DEMO_MATCHES_FILE = Path(__file__).resolve().parents[1] / "resources" / "demo" / "matches_demo.json"
MAX_MATCHES = 50


class MatchService:
    def __init__(self, repository: MatchRepository, client: RiotApiClient | None):
        self.repository = repository
        self.client = client

    @property
    def can_use_api(self) -> bool:
        return self.client is not None

    def link_account(self, platform: Platform, game_name: str, tag_line: str) -> LinkedAccount:
        current = self.repository.get_account()
        if (current and current.platform == platform.value
                and current.game_name.lower() == game_name.lower()
                and current.tag_line.lower() == tag_line.lower()):
            return current
        if not self.client:
            raise RuntimeError("Hace falta una API key de Riot para vincular una cuenta.")
        data = self.client.account_by_riot_id(platform, game_name, tag_line)
        account = LinkedAccount(
            puuid=data["puuid"],
            game_name=data.get("gameName") or game_name,
            tag_line=data.get("tagLine") or tag_line,
            platform=platform.value,
            retrieved_at=datetime.now(timezone.utc),
        )
        self.repository.save_account(account)
        return account

    def fetch_recent(self, account: LinkedAccount, count: int = 20) -> tuple[list[MatchSummary], int]:
        """Descarga las partidas recientes que falten. Devuelve (partidas, nuevas)."""
        if not self.client:
            raise RuntimeError("Hace falta una API key de Riot para descargar partidas.")
        platform = Platform(account.platform)
        ids = self.client.match_ids(platform, account.puuid, count=min(count, MAX_MATCHES))
        new = 0
        for match_id in ids:
            if not self.repository.has_match(match_id):
                self.repository.save_match(match_id, platform.value, self.client.match(platform, match_id))
                new += 1
        return self.stored_matches(account.puuid), new

    def stored_matches(self, puuid: str) -> list[MatchSummary]:
        summaries = []
        for platform, raw in self.repository.all_matches():
            summary = summarize_match(raw, puuid, platform)
            if summary is not None:
                summaries.append(summary)
        return _newest_first(summaries)

    # --- Fase de líneas (timeline) ---------------------------------------------

    def lane_analysis(self, match: MatchSummary, download: bool = True) -> LaneAnalysis | None:
        """Analiza la fase de líneas. Pide el timeline a la API solo si no está guardado."""
        stored = self.repository.get_match(match.match_id)
        if stored is None:
            return None
        _, raw = stored
        timeline = self.repository.get_timeline(match.match_id)
        if timeline is None:
            if not download or not self.client:
                return None
            timeline = self.client.match_timeline(Platform(match.platform), match.match_id)
            self.repository.save_timeline(match.match_id, timeline)
        return analyze_lane(timeline, match, players_from_match(raw))

    def lane_analyses(self, matches: list[MatchSummary], limit: int = 10) -> list[LaneAnalysis]:
        """Fase de líneas de las `limit` partidas más recientes (1 petición por timeline nuevo)."""
        result = []
        for match in matches[:limit]:
            analysis = self.lane_analysis(match)
            if analysis is not None:
                result.append(analysis)
        return result

    # --- Perfil de jugador: rango y maestría --------------------------------------

    def player_profile(self, account: LinkedAccount) -> PlayerProfile:
        if not self.client:
            raise RuntimeError("Hace falta una API key de Riot para consultar el rango y la maestría.")
        platform = Platform(account.platform)
        entries = self.client.league_entries(platform, account.puuid)
        masteries = self.client.mastery_top(platform, account.puuid, count=10)
        return PlayerProfile(
            ranked=[RankedEntry(
                queue=e.get("queueType", ""), tier=e.get("tier", ""), division=e.get("rank", ""),
                lp=e.get("leaguePoints", 0), wins=e.get("wins", 0), losses=e.get("losses", 0),
                hot_streak=bool(e.get("hotStreak")),
            ) for e in entries if isinstance(e, dict)],
            masteries=[MasteryEntry(
                champion_key=m.get("championId", 0), level=m.get("championLevel", 0),
                points=m.get("championPoints", 0),
                last_played=datetime.fromtimestamp(m["lastPlayTime"] / 1000, timezone.utc)
                if isinstance(m.get("lastPlayTime"), int) else None,
            ) for m in masteries if isinstance(m, dict)],
            retrieved_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def demo_matches(path: Path = DEMO_MATCHES_FILE) -> tuple[LinkedAccount, list[MatchSummary]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        account = LinkedAccount(
            puuid=data["puuid"], game_name=data["game_name"], tag_line=data["tag_line"],
            platform=data["platform"], retrieved_at=datetime.now(timezone.utc),
        )
        summaries = [
            s for raw in data["matches"]
            if (s := summarize_match(raw, account.puuid, account.platform, is_demo=True)) is not None
        ]
        return account, _newest_first(summaries)


def _newest_first(matches: list[MatchSummary]) -> list[MatchSummary]:
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(matches, key=lambda m: m.played_at or oldest, reverse=True)
