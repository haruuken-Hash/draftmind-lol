"""Limitador de peticiones por ventanas deslizantes.

La Riot API limita las claves de desarrollo/personales a 20 peticiones por
segundo y 100 cada 2 minutos (por región). Antes de cada petición se llama a
``acquire()``, que espera lo necesario para no superar ningún límite.
Tras un 429, ``pause_for(segundos)`` bloquea todas las peticiones el tiempo
indicado por el encabezado Retry-After.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

DEFAULT_LIMITS = ((20, 1.0), (100, 120.0))


class RateLimiter:
    def __init__(
        self,
        limits: tuple[tuple[int, float], ...] = DEFAULT_LIMITS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._limits = limits
        self._clock = clock
        self._sleep = sleep
        self._history: deque[float] = deque()
        self._paused_until = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                wait = self._wait_time(self._clock())
                if wait <= 0:
                    self._history.append(self._clock())
                    return
            self._sleep(wait)

    def pause_for(self, seconds: float) -> None:
        with self._lock:
            self._paused_until = max(self._paused_until, self._clock() + seconds)

    def _wait_time(self, now: float) -> float:
        wait = self._paused_until - now
        longest = max(window for _, window in self._limits)
        while self._history and now - self._history[0] >= longest:
            self._history.popleft()
        for count, window in self._limits:
            recent = [t for t in self._history if now - t < window]
            if len(recent) >= count:
                wait = max(wait, recent[-count] + window - now)
        return wait
