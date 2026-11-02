# Guía de aprendizaje

Un recorrido sugerido para entender el código, de lo más simple a lo más complejo.

## 1. Qué ocurre al colocar un campeón en el tablero

1. `ui/views/draft_view.py` → `DraftView.place_champion()` coloca el campeón en la casilla activa y llama a `update_analysis()`.
2. `current_draft()` construye un `DraftState` (`domain/models.py`) y lo publica en la sesión (`session.set_draft`), para que «Estrategia» y «Runas y builds» se actualicen.
3. `DraftAnalyzer.analyze_candidate()` (`analysis/draft_analyzer.py`) evalúa seis factores. Cada uno devuelve un `FactorResult`.
4. `assess_confidence()` (`analysis/confidence.py`) decide el nivel de confianza.
5. `RecommendationCard` (`ui/components/recommendation_card.py`) dibuja cada tarjeta.

## 2. Qué ocurre al pulsar «Cargar partidas»

1. `MatchHistoryView.load_from_api()` lanza el trabajo en segundo plano con `run_task()` (`ui/workers.py`).
2. `MatchService.link_account()` traduce el Riot ID a PUUID (solo la primera vez).
3. `fetch_recent()` pide la lista de partidas y descarga solo las que faltan.
4. `RiotApiClient._get()` (`integrations/riot_api.py`):
   - espera al limitador (`utils/rate_limiter.py`);
   - envía la clave en la cabecera;
   - reintenta los errores 5xx;
   - respeta `Retry-After` en los 429.
5. `summarize_match()` (`integrations/riot_match.py`) convierte cada JSON en un `MatchSummary`, comprobando cada campo.
6. La sesión avisa al resto de pantallas con la señal `matches_changed`.

## 3. Conceptos de Python que aparecen

| Concepto | Dónde verlo |
|---|---|
| `Enum` con propiedades | `domain/enums.py` (`Role.label`) |
| Validación con Pydantic, alias de campos | `domain/schemas.py` (`from_` ↔ `"from"`) |
| Clases abstractas (`ABC`) | `integrations/statistics_providers.py` |
| `dataclass` | `app/config.py`, `postgame_analyzer.MatchFilter` |
| ORM con SQLAlchemy 2 | `data/database.py`, `data/repositories/` |
| Hilos y bloqueos | `utils/rate_limiter.py`, `services/catalog_service.py` (`ThreadPoolExecutor`) |
| Señales y slots de Qt | `ui/session.py` |
| Simular la red en pruebas | `tests/unit/test_data_dragon.py` (`httpx.MockTransport`) |
| Inyectar un reloj falso | `tests/unit/test_riot_api.py` (`FakeClock`) |

## 4. Ejercicios propuestos

1. Añade un campeón a `resources/demo/champions_demo.json` y comprueba que participa en el draft. Prueba a poner `"engage": 5` y lee el error de validación.
2. Cambia `TREND_WINDOW` en `postgame_analyzer.py` a 3 y observa cómo cambian las observaciones con las partidas de demostración.
3. Escribe un proveedor de estadísticas nuevo que herede de `StatisticsProvider` y devuelva datos de un diccionario. Conéctalo en `StatsService.providers`.
4. Modifica `tools/generate_demo_matches.py` para que las partidas recientes tengan menos muertes. Vuelve a generarlas y comprueba que la observación de muertes cambia.
