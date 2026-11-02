# Arquitectura

## Capas

```
ui/ ──usa──▶ services/ ──usa──▶ integrations/ (red) y data/ (SQLite)
 │                                     │
 └──usa──▶ analysis/ ──usa──▶ domain/ ◀┘
app/bootstrap.py crea todas las piezas y las agrupa en AppContext.
```

- **domain**: modelos Pydantic (`models.py`), enumeraciones y esquemas de formatos externos (`schemas.py`). No depende de nada más del proyecto.
- **analysis**: lógica pura. No importa Qt ni hace peticiones de red; se prueba rápido y sin ventanas.
- **integrations**: un cliente por fuente externa.
  - `data_dragon.py`: datos estáticos con caché en disco.
  - `riot_api.py`: cuentas y partidas, con limitador de peticiones y reintentos.
  - `riot_match.py`: convierte el JSON de match-v5 en `MatchSummary`.
  - `statistics_providers.py`: interfaz común de estadísticas y sus dos implementaciones.
- **data**: SQLite con SQLAlchemy 2. Los repositorios traducen filas ↔ modelos.
  - `profile_repository`: perfil del usuario.
  - `match_repository`: caché de partidas y cuenta vinculada.
  - `research_repository`: fuentes de investigación.
- **services**: combinan integraciones y datos.
  - `catalog_service`: Data Dragon o demo.
  - `match_service`: Riot API o demo.
  - `stats_service`: proveedores de estadísticas activos.
- **ui**: PySide6.
  - `session.py`: estado compartido entre pantallas, mediante señales.
  - `workers.py`: tareas de red en segundo plano, para que la ventana no se congele.
  - `components/`: piezas reutilizables.
  - `views/`: una pantalla por sección.

## Flujo de datos entre pantallas (`AppSession`)

- **Draft** → `set_draft` → **Estrategia** y **Runas y builds** se actualizan.
- **Historial** → `set_matches` / `set_filtered` → **Análisis postpartida**, y la ventana principal recalcula las estadísticas personales (**Counters** y el factor de enfrentamiento del **Draft**).
- **Historial** (doble clic) → `match_selected` → **Análisis postpartida** muestra esa partida.

## Draft en vivo

```
lockfile ──▶ integrations/league_client.py (GET a 2 rutas, 127.0.0.1)
                 │
                 ▼
         integrations/champ_select.py (sesión → LiveDraft, sin nombres)
                 │
                 ▼
         services/live_draft_service.py (estado: sin cliente / abierto / selección / en partida / error)
                 │  sondeo cada 2 s en segundo plano (ui/workers.py)
                 ▼
         ui/views/draft_view.py: apply_live_draft() rellena el tablero
```

- La activación y la carpeta de instalación se guardan en la tabla `app_setting` (`data/repositories/settings_repository.py`). Por defecto está desactivado.
- `DraftState.bans` hace que los campeones bloqueados no se sugieran.
- Los roles enemigos que indica el usuario se guardan por casilla del cliente (`cellId`) y se conservan entre lecturas.

## Perfiles de campeón

```
Data Dragon (tags, info, alcance) ──▶ analysis/profile_estimator.py ──┐
resources/demo/champions_demo.json (26 editoriales) ──────────────────┼──▶ services/profile_service.build_profiles()
tabla champion_profile_override (revisados por el usuario) ──────────┘            │
                                                                                   ▼
                                                     AppContext.rebuild_profiles() → DraftAnalyzer.set_champions()
```

- Se reconstruyen al arrancar, al descargar Data Dragon y al guardar o restablecer un perfil en «Campeones».
- Si el candidato tiene un perfil estimado, sus factores cualitativos se multiplican por `ESTIMATED_WEIGHT = 0.6`; las estadísticas observadas no se reducen.
- El análisis avisa de qué perfiles del draft son estimados.

## Tipos de evidencia

| Tipo | Significado |
|---|---|
| Dato oficial | Dato estático de Riot (nombres, clases, objetos, runas). No mide rendimiento |
| Estadística observada | Dato medido en una fuente, con muestra, parche y fecha |
| Inferencia estratégica | Razonamiento a partir de datos (p. ej. «aporta primera línea») |
| Sugerencia educativa | Consejo general o dato editorial |
| Evidencia insuficiente | No hay datos para afirmar nada; se dice explícitamente |

## Criterios de confianza (`analysis/confidence.py`)

1. Sin datos → **insuficiente**.
2. Solo datos cualitativos o editoriales → **baja** como máximo.
3. Datos estadísticos según el tamaño de muestra:
   - menos de 100 partidas → insuficiente
   - 100-999 → baja
   - 1000-4999 → media
   - 5000 o más → alta
4. Datos de otro parche, o con más de 14 días: se baja un nivel por cada condición y se muestra una advertencia.

La confianza nunca sube porque una explicación sea más elaborada.

## Analizador de draft (`analysis/draft_analyzer.py`)

Seis factores, cada uno de -2 a +2:

| Factor | Peso | Qué mira |
|---|---|---|
| Encaje de rol | 1.0 | Si el campeón figura en la posición |
| Sinergia con aliados | 1.0 | Primera línea, iniciación, equilibrio de daño y competencia por recursos |
| Respuesta a la composición enemiga | 1.0 | Desenganche frente a iniciación, iniciación frente a poca primera línea y fragilidad frente a mucho control |
| Ventanas de poder | 0.75 | Presión temprana enemiga y equilibrio temprano/tardío |
| Enfrentamiento directo | 0.5 | Ver abajo |
| Preferencias personales | 0.75 | Favoritos y dificultad según el nivel declarado (ajusta, no excluye) |

Factor de enfrentamiento directo:
- Si un proveedor tiene estadísticas del enfrentamiento con confianza al menos baja (≥ 100 partidas), se usa la **estadística observada**: diferencia respecto al 50 % / 10, limitada a ±1.
- Si no, se indica cuántas partidas hay y se hace una comparación cualitativa, limitada a ±0,5.

Puntuación = 50 + 10 × Σ(puntuación × peso), entre 0 y 100.

## Enfrentamientos (`analysis/matchup_analyzer.py`)

Para cada estadística observada se calcula:
- el win rate;
- la **referencia**: el win rate general del campeón en la misma fuente si tiene más partidas, y si no, 50 %;
- la **diferencia** en puntos;
- la confianza según la muestra, el parche y la antigüedad.

Las inferencias cualitativas se formulan como condiciones («puede inclinarse a tu favor si…»), nunca como «counter».

## Builds (`analysis/build_analyzer.py`)

- **Necesidades situacionales** según la composición enemiga:
  - ≥ 70 % de daño de un tipo → resistencias;
  - mucho control → tenacidad;
  - mucha iniciación y campeón frágil → supervivencia;
  - mucha primera línea → penetración.
- **Selección de objetos de ejemplo** por etiquetas oficiales:
  - los objetos centrados en aliados solo se proponen a soportes;
  - los tanques no reciben objetos de daño sin vida;
  - se ordenan por relevancia y luego por precio.
- **Configuraciones frecuentes**: tus partidas (frecuencia, no eficacia).

## Puntuación de rendimiento (`analysis/performance.py`)

Método propio. No es el «OP Score» de OP.GG, cuyo cálculo no es público.

1. Para cada uno de los 10 jugadores se calculan seis métricas: KDA, participación en asesinatos, cuota del daño a campeones de su equipo, oro/min, CS/min y visión/min.
2. En cada métrica se le da una posición relativa entre 0 (el peor de la partida) y 1 (el mejor); los empates comparten valor. A los soportes no se les cuenta el CS.
3. Puntuación = media de esas posiciones × 10.
4. **MVP** = mejor puntuación del equipo ganador; **ACE** = mejor del perdedor.

Solo compara a los jugadores dentro de esa partida: no mide decisiones ni contexto. Si a algún jugador le falta un dato, no se calcula.

## Fase de líneas (`analysis/lane_analyzer.py`)

Usa el timeline de match-v5 (una foto por minuto, estructura comprobada con una partida real):

- Diferencias de oro, CS y experiencia con el rival directo en los minutos 5, 10 y 15. El rival se identifica por la misma `teamPosition` en el otro equipo.
- Primera participación en un asesinato (minuto y posición de la víctima), asesinatos y muertes antes del minuto 15, y objetivos de élite por equipo.
- Tendencia: media de la diferencia de oro y CS en las 10 partidas más recientes (mínimo 3).
- Los timelines se guardan en SQLite (`timeline_cache`) y solo se piden una vez.

## Bloqueos sugeridos (`analysis/ban_analyzer.py`)

Se calculan para tu campeón, si ya lo elegiste, o para tus campeones de confianza: los 3 más jugados en esa posición o, si no hay partidas, los de más maestría. Cada sugerencia suma:

- **Tus partidas** (observado): rivales directos con más del 50 % de derrotas y al menos 2 partidas. Peso completo a partir de 6 partidas.
- **Perfiles** (inferencia, × 0,5; × 0,6 si es estimado): rivales de tu posición con más presión temprana, más escalado, iniciación contra campeones sin desenganche, o mucho control contra campeones frágiles.
- **Estadísticas importadas** (observado): enfrentamientos con win rate por debajo del 48 % y al menos 100 partidas.

Se excluyen los campeones ya elegidos o bloqueados. Cada sugerencia muestra sus motivos y su tipo de evidencia.

## Postpartida (`analysis/postgame_analyzer.py`)

- KDA = (asesinatos + asistencias) / max(muertes, 1).
- CS/min, participación en asesinatos y visión por minuto.
- Tendencias: compara tus 5 partidas más recientes con las 5 anteriores. Hacen falta al menos 3 en cada grupo; si el cambio es menor del 10 %, se considera estable.
- Las observaciones describen resultados y proponen preguntas; no juzgan decisiones.
