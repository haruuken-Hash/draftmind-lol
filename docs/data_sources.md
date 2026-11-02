# Fuentes de datos

Solo se documenta lo comprobado. Fecha de las comprobaciones: 28/10/2026.

## Resumen

| Fuente | Estado | Tipo de evidencia | Autenticación |
|---|---|---|---|
| Data Dragon | En uso | Dato oficial (estático) | Ninguna |
| Riot API (account-v1, match-v5) | En uso, opcional | Estadística observada (tus partidas) | API key (`X-Riot-Token`) |
| Estadísticas importadas (JSON) | En uso, opcional | Estadística observada (según la fuente) | No aplica |
| Perfiles cualitativos de demo | En uso | Sugerencia educativa | No aplica |
| League Client API | En uso, **opcional y desactivada por defecto** (draft en vivo) | Lo que muestra tu propio cliente | Lockfile local |
| OP.GG, U.GG y similares | **No se usan** | — | — |

## Data Dragon

| | |
|---|---|
| Qué ofrece | Datos **estáticos** oficiales: campeones, objetos, runas, hechizos e imágenes |
| API | Archivos JSON e imágenes en un CDN público |
| Autenticación | Ninguna |
| Límites | No he encontrado límites documentados. La app descarga cada archivo una sola vez, consulta las versiones como mucho cada 6 h y descarga como máximo 8 imágenes a la vez |
| Parche / región | Una versión por parche (p. ej. `16.21.1`), sin región. Riot indica que se actualiza a mano y puede tardar tras un parche |
| Idioma | `es_MX` (comprobado en `languages.json`). Si falta para una versión, se usa `en_US` y se avisa |
| Qué NO ofrece | Win rates, pick/ban rates ni ningún dato de rendimiento |
| Alternativa | Caché local; si nunca se descargó, el catálogo de demostración |

Endpoints:
- `/api/versions.json`
- `/cdn/{versión}/data/{idioma}/champion.json`, `item.json`, `summoner.json` y `runesReforged.json`
- `/cdn/{versión}/img/champion/{archivo}`, `/img/item/{id}.png` y `/img/spell/{archivo}`
- `/cdn/img/{icono}` para las runas: **sin versión** en la URL

Detalles comprobados:
- Una versión o idioma inexistente responde **403**.
- `item.json` contiene 863 entradas, con copias para otros modos que usan ID de 6 cifras (p. ej. Arena). La app solo toma objetos de la Grieta con ID de hasta 4 cifras, comprables y con coste ≥ 900 (124 en 16.21.1).
- De `summoner.json` solo se muestran los hechizos con el modo `CLASSIC`.

## Riot API

| | |
|---|---|
| Qué ofrece | Cuenta por Riot ID y partidas de un jugador (estadísticas finales por partida) |
| Autenticación | Cabecera `X-Riot-Token`. Con una clave falsa responde 401 «Unknown apikey» (comprobado) |
| Límites (clave personal o de desarrollo) | 20 peticiones/s y 100 cada 2 min, **por región**. Ante un 429, esperar lo que indique `Retry-After` |
| Caducidad | Las claves de desarrollo caducan cada 24 h |
| Uso permitido | Las claves personales son para proyectos de uso propio, no para productos públicos |
| Alternativa | Partidas FICTICIAS de demostración, marcadas como tales en toda la interfaz |

Campos de match-v5 usados, con su significado según el esquema oficial:
- `info.gameDuration`: en **milisegundos** antes del parche 11.20 y en segundos después. Si existe `gameEndTimestamp`, son segundos.
- `championName`: Riot lo recomienda frente a `championId` para partidas antiguas.
- `gameVersion`: sus dos primeras partes indican el parche.
- `teamPosition`: puede llegar vacío.
- CS = `totalMinionsKilled` + `neutralMinionsKilled`.
- Participación en asesinatos = (asesinatos + asistencias) / asesinatos del equipo. Se calcula solo si están todos los datos.
- `perks.styles[].selections[].perk`: la primera selección del árbol principal es la runa clave.

Cualquier campo ausente queda vacío y su métrica no se calcula. Las partidas de menos de 5 minutos se marcan como posible remake y no cuentan en medias ni tendencias.

No se usa el endpoint `timeline`: la app no reconstruye movimientos ni decisiones.

Más detalles en [riot_api_setup.md](riot_api_setup.md).

## Estadísticas públicas: por qué no hay una integración directa

No he encontrado ninguna API pública, documentada y gratuita de estadísticas agregadas (win rate por campeón o enfrentamiento) cuyas condiciones permitan reutilizar los datos. En particular, no se supone que OP.GG o U.GG ofrezcan una, y la app no usa endpoints privados ni scraping.

Por eso hay una **interfaz de proveedor intercambiable** (`integrations/statistics_providers.py`) con dos implementaciones:

1. **Tus partidas** (`PersonalStatsProvider`): estadísticas reales calculadas a partir de tus partidas de la Riot API. Las muestras son pequeñas y la app lo indica. Si mezclas parches, se avisa.
2. **Archivo importado** (`ImportedStatsProvider`): datos de una fuente que tú elijas y cuyo uso lo permita.

### Formato del archivo de importación

Ejemplo de formato con valores ficticios: [examples/stats_import_example.json](examples/stats_import_example.json).

```json
{
  "source": {"name": "…", "url": "https://…", "retrieved_at": "2026-10-28T12:00:00Z", "notes": "…"},
  "patch": "16.21",
  "region": "LAN",
  "rank_segment": "…",
  "rows": [
    {"champion_id": "Garen", "role": "TOP", "games": 1234, "win_rate": 0.51},
    {"champion_id": "Garen", "role": "TOP", "opponent_id": "Darius", "games": 321, "wins": 150}
  ]
}
```

Reglas del formato:
- **Obligatorios:** `source` (con nombre, URL y fecha de consulta), `patch` y, en cada fila, `champion_id` y `games`.
- **Opcionales:** `role`, `opponent_id`, `wins`, `win_rate`, `pick_rate` y `ban_rate`. Si faltan, quedan vacíos: nunca se rellenan.
- `win_rate`, `pick_rate` y `ban_rate` van como **proporción** (0-1), no como porcentaje.
- `champion_id` es el identificador de Data Dragon (`MonkeyKing`, no «Wukong»).
- `role` acepta `TOP`, `JUNGLE`, `MIDDLE`, `BOTTOM` o `UTILITY`.
- Una fila con `opponent_id` es un enfrentamiento; sin él, es una estadística general del campeón.

Cuando se comparan datos de parches, regiones o segmentos distintos, la app lo advierte.

## Perfiles cualitativos

Cada campeón tiene un perfil de valoraciones 0-3 con uno de tres orígenes. Para un mismo campeón, cada uno sustituye al anterior:

1. **Estimación automática** (`analysis/profile_estimator.py`): reglas a partir de datos oficiales de Data Dragon (`tags`, `info` 0-10 y `stats.attackrange`). Cubre todos los campeones. Su peso en el análisis se reduce al 60 % y se marca en la interfaz.
2. **Editorial de demostración**: 26 perfiles escritos a mano.
3. **Revisado por ti**: editado en «Campeones» y guardado en SQLite (tabla `champion_profile_override`).

Ninguno es una estadística ni pertenece a un parche, así que la confianza del análisis que se basa en ellos nunca supera «baja».

**Fiabilidad de la estimación**, medida frente a los 26 perfiles editoriales (que también son criterio propio, no una verdad absoluta), con Data Dragon 16.21.1:

| Atributo | Error medio | Valor exacto | A ±1 |
|---|---|---|---|
| Iniciación | 0,62 | 15/26 | 22/26 |
| Desenganche | 0,38 | 16/26 | 26/26 |
| Control de masas | 0,42 | 17/26 | 24/26 |
| Presión temprana | 0,65 | 13/26 | 22/26 |
| Escalado | 0,54 | 14/26 | 24/26 |
| Primera línea | 0,38 | 17/26 | 25/26 |
| Dificultad | 0,54 | 12/26 | 26/26 |
| Dependencia de recursos | 0,54 | 12/26 | 26/26 |

Además coincide el tipo de daño en 19/26 y la posición en 21/26.

**Posiciones observadas.** Los datos oficiales no indican qué campeones van a jungla, así que la clase sola nunca asigna esa posición. Por eso, en los perfiles **estimados**, las posiciones se corrigen con las partidas reales descargadas con la Riot API (`services/profile_service.observed_positions`):

- Se cuenta la `teamPosition` de los **10 jugadores** de cada partida, sin contar remakes ni partidas de demostración.
- Una posición se acepta si aparece al menos 2 veces y en al menos el 25 % de las apariciones del campeón.
- La ficha del campeón indica en cuántas apariciones se basa.
- Los perfiles editoriales y los revisados por ti no se modifican.

Ejemplo real (01/11/2026, 50 partidas): Kayn, Lillia, Shaco, Nocturne y Briar pasaron de Superior o Medio a Jungla.

## League Client API (draft en vivo)

Es una API local del cliente de LoL. Se activa en «Fuentes y configuración» → «Draft en vivo».

**Lo comprobado en fuentes oficiales** (30/10/2026):
- Según la [documentación de Riot](https://developer.riotgames.com/docs/lol#league-client-api), **no tiene soporte oficial**: no hay garantías de documentación, disponibilidad ni aviso de cambios. Puede dejar de funcionar con un parche. Riot pide registrar su uso en el Developer Portal.
- La misma documentación indica que el cliente usa un certificado autofirmado y publica el certificado raíz. Va incluido en `src/draftmind/resources/certs/riotgames.pem`: «LoL Game Engineering Certificate Authority», válido hasta 2043.

**Lo que NO está en documentación oficial**, pero **se comprobó con el cliente real el 01/11/2026** (partida personalizada a ciegas, versión del cliente de esa fecha):
- El formato del lockfile: `nombre:pid:puerto:contraseña:protocolo`.
- `/lol-gameflow/v1/gameflow-phase` devuelve un texto: `"None"` en el menú, `"ChampSelect"` en la selección y `"InProgress"` en partida.
- `/lol-champ-select/v1/session` contiene `localPlayerCellId`, `myTeam`/`theirTeam` (con `cellId`, `championId`, `championPickIntent` y `assignedPosition`), `bans` (`myTeamBans`, `theirTeamBans`, `numBans`), `actions` (listas de acciones con `type`, `championId` y `completed`) y otros campos que no se usan.
- En la selección a ciegas, el jugador local llega con `assignedPosition` vacío; los aliados bot sí traen posición.
- La respuesta incluye campos de identidad (`gameName`, `tagLine`, `puuid`, `summonerId`...) que la app descarta sin leerlos.
- El certificado del cliente está firmado por la CA de Riot, pero no incluye el campo «Authority Key Identifier». Python 3.13 lo rechaza en modo estricto (`VERIFY_X509_STRICT`), así que se desactiva solo ese modo estricto y se sigue validando la firma.

Como Riot no garantiza este formato, el intérprete (`integrations/champ_select.py`) sigue ignorando cualquier campo ausente o con otro tipo. Pendiente de comprobar en partidas reales: bloqueos y selección por turnos (draft de clasificatorias).

**Cómo funciona:**
1. Lee el archivo `lockfile` de la carpeta de instalación (por defecto `C:\Riot Games\League of Legends`). No lee otros procesos ni su memoria.
2. Cada 2 segundos hace como mucho dos peticiones GET a `127.0.0.1`, solo a las dos rutas de una lista cerrada.
3. Valida el certificado con la CA de Riot. Si no encaja, continúa sin verificación, porque la conexión es local, y lo indica en pantalla.

**Restricciones aplicadas**, según la [política de aplicaciones de terceros](https://support.riotgames.com/es-es/riot/events/third-party-applications) y el resumen de requisitos de Riot en la [guía de cumplimiento de Overwolf](https://dev.overwolf.com/ow-native/guides/game-compliance/riot-games):
- **Solo lectura:** el código no tiene ninguna petición que elija, bloquee o modifique nada.
- **Anonimato:** no se lee ningún nombre ni identificador de jugador. Las pruebas comprueban que esos campos se descartan.
- **Rivales:** solo se usan los campeones que el cliente muestra como elegidos, nunca sus intenciones. Los roles enemigos quedan como «Rol ?» salvo que tú los indiques.
- **Durante la partida** (fases GameStart, InProgress y Reconnect): no se lee la sesión ni se actualiza el tablero.
- **Desactivado por defecto.**

Cuando el cliente no está abierto, la app lo indica y el tablero sigue funcionando a mano. Con «Pausar seguimiento» puedes editarlo libremente.

## Investigación web y modelos de lenguaje

La sección «Investigación» registra fuentes (URL, título, tipo, fecha de publicación si se conoce, fecha de consulta, parche, afirmación y estado de verificación). Nada se marca como verificado por defecto, y separa las fuentes oficiales de los análisis y opiniones.

No hay integración con modelos de lenguaje: ninguna función principal la necesita. Si se añadiera, solo debería usar como contexto datos recuperados y validados, y reconocer cuándo falta evidencia.
