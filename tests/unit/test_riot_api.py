"""Cliente de la Riot API con respuestas simuladas: no usa claves ni Internet."""

import httpx
import pytest

from draftmind.integrations.riot_api import (
    Platform,
    RiotApiClient,
    RiotApiError,
    RiotAuthError,
    RiotNotFound,
    RiotRateLimited,
)
from draftmind.utils.rate_limiter import RateLimiter

KEY = "RGAPI-clave-de-prueba"


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(handler, clock=None, max_retries=3):
    clock = clock or FakeClock()
    limiter = RateLimiter(clock=clock.time, sleep=clock.sleep)
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return RiotApiClient(KEY, http=http, limiter=limiter, sleep=clock.sleep, max_retries=max_retries), clock


def test_sends_key_in_header_and_uses_routing():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"puuid": "P", "gameName": "Ana", "tagLine": "LAN"})

    client, _ = make_client(handler)
    client.account_by_riot_id(Platform.LA1, "Ana Pérez", "LAN")
    request = seen[0]
    assert request.headers["X-Riot-Token"] == KEY
    assert request.url.host == "americas.api.riotgames.com"
    assert request.url.raw_path.decode().endswith("/by-riot-id/Ana%20P%C3%A9rez/LAN")
    assert KEY not in str(request.url)  # La clave nunca va en la URL.


def test_routing_regions():
    assert Platform.EUW1.match_region == "europe"
    assert Platform.KR.match_region == "asia"
    assert Platform.OC1.match_region == "sea"
    assert Platform.OC1.account_region == "asia"  # account-v1 no ofrece SEA.


def test_match_ids_count_is_clamped():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=["LA1_1"])

    client, _ = make_client(handler)
    client.match_ids(Platform.LA1, "P", count=500)
    assert seen[0].url.params["count"] == "100"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_are_readable_and_hide_key(status):
    client, _ = make_client(lambda r: httpx.Response(status))
    with pytest.raises(RiotAuthError) as info:
        client.match(Platform.LA1, "LA1_1")
    assert "24 horas" in str(info.value)
    assert KEY not in str(info.value)


def test_not_found():
    client, _ = make_client(lambda r: httpx.Response(404))
    with pytest.raises(RiotNotFound):
        client.account_by_riot_id(Platform.LA1, "Nadie", "000")


def test_429_respects_retry_after_then_succeeds():
    responses = [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": True})]
    client, clock = make_client(lambda r: responses.pop(0))
    assert client.match(Platform.LA1, "LA1_1") == {"ok": True}
    assert 7 in clock.sleeps  # Esperó lo que pidió el servidor antes de reintentar.


def test_persistent_429_gives_up():
    client, _ = make_client(lambda r: httpx.Response(429, headers={"Retry-After": "2"}), max_retries=2)
    with pytest.raises(RiotRateLimited):
        client.match(Platform.LA1, "LA1_1")


def test_server_errors_are_retried_with_backoff():
    responses = [httpx.Response(503), httpx.Response(500), httpx.Response(200, json=[])]
    client, clock = make_client(lambda r: responses.pop(0))
    assert client.match_ids(Platform.LA1, "P") == []
    assert clock.sleeps[:2] == [1, 2]


def test_connection_error_after_retries():
    def handler(request):
        raise httpx.ConnectError("sin red", request=request)

    client, _ = make_client(handler, max_retries=1)
    with pytest.raises(RiotApiError, match="No se pudo conectar"):
        client.match(Platform.LA1, "LA1_1")


def test_missing_key_is_rejected():
    with pytest.raises(RiotAuthError):
        RiotApiClient("")


def test_rate_limiter_waits_when_window_is_full():
    clock = FakeClock()
    limiter = RateLimiter(limits=((2, 1.0),), clock=clock.time, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()
    assert clock.now == pytest.approx(1.0)  # La tercera petición esperó 1 s.


def test_rate_limiter_long_window():
    clock = FakeClock()
    limiter = RateLimiter(limits=((20, 1.0), (100, 120.0)), clock=clock.time, sleep=clock.sleep)
    for _ in range(101):
        limiter.acquire()
    assert clock.now >= 120.0  # La petición 101 esperó a que se liberara la ventana de 2 min.
