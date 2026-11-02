# DraftMind LoL

Asistente de escritorio para Windows que ayuda a **estudiar** drafts y partidas de League of Legends. Es un proyecto personal y de aprendizaje: el código está comentado en español para que se pueda seguir.

> Las recomendaciones son ayudas para razonar, no certezas. Cada una indica qué datos usa, de qué tipo son (dato oficial, estadística observada, inferencia estratégica, sugerencia educativa o evidencia insuficiente) y con qué confianza.

## Estado actual (versión 0.6.0)

Inspirada en las funciones de OP.GG e iTero que se pueden ofrecer de forma legítima (ver la tabla de abajo).

| Sección | Qué hace |
|---|---|
| Inicio | Banner con tu campeón más jugado, forma reciente, cifras principales y accesos rápidos |
| Mi perfil | Rango y LP (league-v4), maestría (champion-mastery-v4), win rate, KDA, CS/min, puntuación media, MVP/ACE, tabla por campeón y reparto de posiciones |
| Campeones | Los 173 campeones oficiales con retrato, buscador, filtro por clase y ficha con el perfil de análisis; **editor** para revisar cualquier perfil |
| Draft | Tablero 5 contra 5 interactivo con análisis en vivo, tarjetas de recomendación e informe completo. Opcionalmente, **sigue la selección de campeones de tu cliente** (solo lectura) |
| Counters | Tu campeón contra un rival: estadísticas observadas con muestra, diferencia respecto a una referencia, condiciones del enfrentamiento y tus enfrentamientos observados |
| Runas y builds | Necesidades situacionales según el draft, orientación de runas y hechizos, tus configuraciones frecuentes y exploradores de objetos, runas y hechizos oficiales |
| Estrategia | Hechos del draft, condiciones de victoria, ventanas de poder, riesgos y preguntas para la partida |
| Historial | Tus partidas mediante la Riot API (o partidas ficticias de demostración), con filtros por campeón, posición, periodo y resultado |
| Análisis postpartida | Detalle de una partida, medias, gráficas de evolución y observaciones educativas |
| Investigación | Registro de fuentes (oficiales u opiniones) con su verificación |
| Fuentes y configuración | API key (sin mostrarla), Data Dragon, importación de estadísticas, cachés y perfil personal |

Novedades de la 0.6.0, además del rediseño visual:

- **Puntuación de rendimiento** 0-10 por partida, con MVP y ACE, comparada con los 10 jugadores de cada partida. Se muestra en «Historial» y «Análisis postpartida».
- **Fase de líneas**: oro, CS y experiencia a los 5, 10 y 15 min frente a tu rival directo, primera participación en un asesinato, objetivos tempranos y tendencia de tus últimas 10 partidas (timeline oficial).
- **Bloqueos sugeridos** en «Draft», según tus derrotas reales como rival directo, los perfiles y las estadísticas importadas.
- **Habilidades y consejos oficiales de Riot** por campeón («Campeones») y cómo jugar contra tu rival («Counters»).

### Qué hay de OP.GG e iTero y qué no

| Función | ¿Incluida? | Motivo |
|---|---|---|
| Perfil con rango, maestría y estadísticas por campeón | Sí | Riot API oficial + tus partidas |
| Puntuación por partida, MVP/ACE | Sí (método propio y documentado) | El cálculo de OP.GG no es público |
| Sugerencias de bloqueo | Sí (personalizadas) | Tus partidas, perfiles y estadísticas importadas |
| Análisis de la fase de líneas | Sí | Timeline oficial |
| Tier lists y builds «más populares» globales | No | Hacen falta estadísticas de millones de partidas que no hay de forma legítima; se pueden importar en «Configuración» |
| Overlays y temporizadores durante la partida | No | Prohibido por la política de Riot |
| Ver a los jugadores en la selección de clasificatorias | No | Prohibido (anonimato) |
| Aplicar runas automáticamente en el cliente | No | La app solo lee el cliente, nunca escribe |

### Draft en vivo

Desactivado por defecto. Para usarlo:
1. Ve a «Fuentes y configuración» → «Draft en vivo» y marca «Activar el draft en vivo».
2. Comprueba la carpeta de League of Legends (por defecto `C:\Riot Games\League of Legends`).
3. Abre el cliente y entra en una selección de campeones: el tablero de «Draft» se rellena solo con tu posición, tus aliados (los campeones en hover aparecen como «sin confirmar»), los rivales ya elegidos y los bloqueos. Los campeones bloqueados no se sugieren.
4. Indica a mano los roles enemigos si los deduces: se conservan entre actualizaciones.

Garantías:
- solo lectura;
- sin nombres de jugadores;
- se detiene durante la partida;
- usa una API local que Riot no soporta oficialmente, así que puede romperse con un parche.

Detalles en [docs/data_sources.md](docs/data_sources.md).

## Instalación en Windows

Requisitos: Python 3.13 (probado con 3.13.14).

```bash
cd draftmind-lol
```

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Opcional: copia `.env.example` como `.env`. Sin clave de Riot todo funciona en **modo demostración**. Para usar tus partidas reales, sigue [docs/riot_api_setup.md](docs/riot_api_setup.md).

## Ejecución

```bash
.venv\Scripts\python.exe main.py
```

Atajos de teclado:
- `Ctrl+1` … `Ctrl+9` y `Ctrl+0` cambian de sección.
- En «Draft»: `Ctrl+F` busca, `Esc` cancela la selección y `Supr` vacía una casilla.

## Pruebas

```bash
.venv\Scripts\python.exe -m pytest -q
```

Las pruebas no usan Internet ni API keys: Data Dragon y la Riot API se simulan con respuestas grabadas. La interfaz se prueba sin mostrar ventanas.

## Empaquetado (ejecutable de Windows)

```bash
powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1
```

El script ejecuta las pruebas y, si pasan, genera `dist\DraftMindLoL\DraftMindLoL.exe` (unos 190 MB en total, sobre todo por PySide6 y Matplotlib). Copia la carpeta `dist\DraftMindLoL` completa: el `.exe` necesita los archivos que lo acompañan. El ejecutable no incluye ninguna clave; para usar la Riot API, pon un `.env` junto al `.exe`.

## Datos de demostración

- `src/draftmind/resources/demo/champions_demo.json`: 26 perfiles cualitativos escritos a mano (0-3). **No son estadísticas.**
- `src/draftmind/resources/demo/matches_demo.json`: 14 partidas **ficticias** generadas por `tools/generate_demo_matches.py`. Se marcan como tales en toda la interfaz.
- `docs/examples/stats_import_example.json`: ejemplo del formato de importación con valores ficticios.

## Dónde se guardan los datos

Por defecto en `%LOCALAPPDATA%\DraftMindLoL`:
- `draftmind.db`: perfil, partidas, cuenta vinculada y fuentes de investigación.
- `logs\draftmind.log`
- `cache\ddragon\`: unos 8 MB por versión.
- `stats_import.json`: si importas estadísticas.

**Si usas el Python de Microsoft Store**, Windows redirige esa carpeta a `%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.3.13_...\LocalCache\Local\DraftMindLoL`. Puedes elegir otra con `DRAFTMIND_DATA_DIR` en `.env`.

## Estructura

```
main.py                        Punto de entrada
src/draftmind/
  app/           config.py (.env), bootstrap.py (monta la aplicación)
  domain/        enums.py, models.py, schemas.py (formatos externos)
  data/          database.py (SQLAlchemy), demo_data.py, repositories/
  integrations/  data_dragon.py, riot_api.py, riot_match.py, statistics_providers.py
  services/      catalog_service.py, match_service.py, stats_service.py
  analysis/      confidence.py, composition_analyzer.py, draft_analyzer.py, matchup_analyzer.py,
                 build_analyzer.py, strategy_analyzer.py, postgame_analyzer.py
  ui/            main_window.py, session.py, theme.py, workers.py, portraits.py, components/, views/
  resources/demo/
  utils/         logging_config.py, rate_limiter.py, text.py
tests/           unit/, integration/, fixtures/
tools/           generate_demo_matches.py, build_windows.ps1
docs/            architecture.md, data_sources.md, riot_api_setup.md, learning_guide.md, examples/
```

## Limitaciones conocidas

- **Estadísticas:** no hay fuente pública de estadísticas agregadas conectada. Las tuyas tienen muestras pequeñas y casi siempre dan «evidencia insuficiente» para conclusiones estadísticas; la app lo indica en lugar de inventar cifras.
- **Perfiles cualitativos:** 26 son editoriales y el resto se **estiman automáticamente** a partir de datos oficiales. Las estimaciones pesan menos, y sus posiciones se corrigen con las observadas en tus partidas descargadas (así aparecen los junglas). Puedes revisar cualquier perfil en «Campeones» → «Revisar perfil»; tu revisión tiene prioridad. Fiabilidad medida en [docs/data_sources.md](docs/data_sources.md).
- **Builds:** las sugerencias de objetos se basan en etiquetas oficiales y reglas sencillas; son ejemplos, no la build óptima. No se evalúan la curación ni los escudos enemigos.
- **Postpartida:** usa estadísticas finales; no analiza movimientos ni decisiones (no se usa el timeline).
- **Enrutamiento:** la correspondencia entre plataformas y regiones de la Riot API es la convención habitual, no una tabla de la documentación.
- **Puntuación:** la puntuación 0-100 del draft solo sirve para comparar candidatos dentro del mismo draft; no es un win rate.
- **Draft en vivo:** el formato de la sesión del cliente no está documentado por Riot. Se comprobó con el cliente real en una partida personalizada a ciegas (selección, posiciones y paso a partida); los **bloqueos y el draft por turnos de clasificatorias aún no se han visto en un cliente real**.

## Cumplimiento

La aplicación no lee la memoria del juego ni otros procesos, no automatiza acciones, no elige ni bloquea campeones y no muestra información oculta ni nombres de jugadores en la selección de campeones. Solo analiza lo que introduces, lo que muestra tu propio cliente (si activas el draft en vivo) y datos de fuentes oficiales o importadas por ti.

DraftMind LoL isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
