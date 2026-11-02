"""Cliente de la Riot API oficial (account-v1 y match-v5).

Comprobado el 28/10/2026 en developer.riotgames.com:
- Autenticación: cabecera ``X-Riot-Token``. Una clave inválida responde 401
  ("Unknown apikey"). Las claves de desarrollo caducan cada 24 horas.
- account-v1: /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}
  en AMERICAS, ASIA o EUROPE ("se puede consultar cualquier cuenta en
  cualquier región").
- match-v5: /lol/match/v5/matches/by-puuid/{puuid}/ids (count 0-100,
  por defecto 20) y /lol/match/v5/matches/{matchId}, en la región de
  enrutamiento (AMERICAS, ASIA, EUROPE, SEA).
- 429: detener las peticiones los segundos que indique Retry-After.
- Límites de clave personal: 20 peticiones/s y 100 cada 2 min, por región.

La clave nunca se escribe en registros ni en mensajes de error.
"""

import logging
import time
from collections.abc import Callable
from enum import Enum
from typing import Any
from urllib.parse import quote

import httpx

from draftmind.utils.rate_limiter import RateLimiter

log = logging.getLogger(__name__)

MAX_RETRIES = 3


class Platform(str, Enum):
    """Plataformas listadas en la documentación de enrutamiento de Riot."""

    BR1 = "BR1"
    EUN1 = "EUN1"
    EUW1 = "EUW1"
    JP1 = "JP1"
    KR = "KR"
    LA1 = "LA1"
    LA2 = "LA2"
    NA1 = "NA1"
    OC1 = "OC1"
    TR1 = "TR1"
    RU = "RU"
    PH2 = "PH2"
    SG2 = "SG2"
    TH2 = "TH2"
    TW2 = "TW2"
    VN2 = "VN2"

    @property
    def label(self) -> str:
        return _PLATFORM_LABELS[self]

    @property
    def match_region(self) -> str:
        """Región de enrutamiento para match-v5."""
        return _MATCH_REGION[self]

    @property
    def account_region(self) -> str:
        # account-v1 solo expone AMERICAS, ASIA y EUROPE y admite cualquier cuenta.
        return "asia" if self.match_region == "sea" else self.match_region


_PLATFORM_LABELS = {
    Platform.LA1: "LAN (Latinoamérica Norte)", Platform.LA2: "LAS (Latinoamérica Sur)",
    Platform.NA1: "NA (Norteamérica)", Platform.BR1: "BR (Brasil)",
    Platform.EUW1: "EUW (Europa Oeste)", Platform.EUN1: "EUNE (Europa Nórdica y Este)",
    Platform.TR1: "TR (Turquía)", Platform.RU: "RU (Rusia)", Platform.KR: "KR (Corea)",
    Platform.JP1: "JP (Japón)", Platform.OC1: "OCE (Oceanía)", Platform.PH2: "PH (Filipinas)",
    Platform.SG2: "SG (Singapur)", Platform.TH2: "TH (Tailandia)", Platform.TW2: "TW (Taiwán)",
    Platform.VN2: "VN (Vietnam)",
}

# Agrupación convencional de plataformas por región de enrutamiento.
_MATCH_REGION = {
    Platform.NA1: "americas", Platform.BR1: "americas", Platform.LA1: "americas", Platform.LA2: "americas",
    Platform.EUW1: "europe", Platform.EUN1: "europe", Platform.TR1: "europe", Platform.RU: "europe",
    Platform.KR: "asia", Platform.JP1: "asia",
    Platform.OC1: "sea", Platform.PH2: "sea", Platform.SG2: "sea", Platform.TH2: "sea",
    Platform.TW2: "sea", Platform.VN2: "sea",
}


class RiotApiError(Exception):
    """Error comprensible para el usuario."""


class RiotAuthError(RiotApiError):
    pass


class RiotNotFound(RiotApiError):
    pass


class RiotRateLimited(RiotApiError):
    pass


class RiotApiClient:
    def __init__(
        self,
        api_key: str,
        http: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = MAX_RETRIES,
    ):
        if not api_key:
            raise RiotAuthError("No hay API key de Riot configurada.")
        self._key = api_key
        self._http = http or httpx.Client(timeout=20)
        self._limiter = limiter or RateLimiter()
        self._sleep = sleep
        self._max_retries = max_retries

    def _get(self, host: str, path: str, params: dict | None = None) -> Any:
        url = f"https://{host}.api.riotgames.com{path}"
        for attempt in range(self._max_retries + 1):
            self._limiter.acquire()
            try:
                response = self._http.get(url, params=params, headers={"X-Riot-Token": self._key})
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    self._sleep(2 ** attempt)
                    continue
                raise RiotApiError(f"No se pudo conectar con la Riot API ({exc.__class__.__name__}).") from None

            status = response.status_code
            if status == 200:
                return response.json()
            if status in (401, 403):
                raise RiotAuthError(
                    "La Riot API rechazó la clave: no es válida, ha caducado (las de desarrollo duran "
                    "24 horas) o no tiene acceso a este recurso."
                )
            if status == 404:
                raise RiotNotFound("No se encontró el recurso solicitado (revisa el Riot ID y la región).")
            if status == 429:
                retry_after = _retry_after_seconds(response)
                log.warning("Límite de la Riot API alcanzado; pausa de %.0f s.", retry_after)
                self._limiter.pause_for(retry_after)
                if attempt < self._max_retries:
                    continue
                raise RiotRateLimited(f"Límite de peticiones alcanzado. Inténtalo en {retry_after:.0f} s.")
            if status >= 500 and attempt < self._max_retries:
                self._sleep(2 ** attempt)
                continue
            raise RiotApiError(f"La Riot API respondió con el código {status}.")
        raise RiotApiError("No se pudo completar la petición a la Riot API.")

    # --- Endpoints ---------------------------------------------------------

    def account_by_riot_id(self, platform: Platform, game_name: str, tag_line: str) -> dict:
        path = f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
        return self._get(platform.account_region, path)

    def match_ids(self, platform: Platform, puuid: str, count: int = 20, queue: int | None = None) -> list[str]:
        params: dict[str, int] = {"start": 0, "count": max(1, min(count, 100))}
        if queue is not None:
            params["queue"] = queue
        return self._get(platform.match_region, f"/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids", params)

    def match(self, platform: Platform, match_id: str) -> dict:
        return self._get(platform.match_region, f"/lol/match/v5/matches/{quote(match_id, safe='')}")


def _retry_after_seconds(response: httpx.Response) -> float:
    try:
        return max(1.0, float(response.headers.get("Retry-After", "1")))
    except ValueError:
        return 1.0
