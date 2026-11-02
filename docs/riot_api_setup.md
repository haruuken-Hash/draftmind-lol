# Configurar la Riot API

La clave solo hace falta para ver **tus partidas reales** en «Historial» y «Análisis postpartida», y para las estadísticas personales de «Counters». Todo lo demás funciona sin ella.

## 1. Conseguir una clave

1. Entra en <https://developer.riotgames.com/> con tu cuenta de Riot.
2. En el panel aparece una **Development API Key**. Caduca cada **24 horas** y hay que regenerarla en el mismo panel.
3. Para uso continuado puedes registrar un producto personal y pedir una **Personal API Key**, pensada para proyectos de uso propio o de una comunidad pequeña. Es la que corresponde a esta aplicación.

Límites de las claves personales y de desarrollo (documentación de Riot, 28/10/2026): **20 peticiones por segundo y 100 cada 2 minutos**, por región. La aplicación los respeta: espera lo necesario y, ante un error 429, se detiene los segundos que indique la cabecera `Retry-After`.

## 2. Guardarla sin exponerla

1. Copia `.env.example` como `.env` en la carpeta del proyecto. Con el ejecutable, ponlo junto a `DraftMindLoL.exe`.
2. Escribe la clave:

   ```
   RIOT_API_KEY=RGAPI-...
   ```

3. Reinicia la aplicación. En «Fuentes y configuración» verás «Configurada (el valor no se muestra)».

La clave:
- **no** se escribe en los registros ni en los mensajes de error;
- se envía solo en la cabecera `X-Riot-Token`, nunca en la URL;
- **no** se incluye en Git (`.gitignore`) ni en el ejecutable.

No la compartas ni la pegues en capturas.

## 3. Uso

En «Historial», escribe tu Riot ID completo (`Nombre#ETIQUETA`), elige tu servidor y pulsa «Cargar partidas».

| Paso | Endpoint | Cuándo |
|---|---|---|
| Riot ID → PUUID | `account-v1 /riot/account/v1/accounts/by-riot-id/{nombre}/{etiqueta}` | Solo la primera vez; el PUUID se guarda |
| Lista de partidas | `match-v5 /lol/match/v5/matches/by-puuid/{puuid}/ids?count=N` | En cada carga (N ≤ 50 en la app; la API admite hasta 100) |
| Detalle | `match-v5 /lol/match/v5/matches/{id}` | Solo para partidas que no estén guardadas |

Las partidas se guardan en SQLite: una partida terminada no cambia, así que nunca se vuelve a pedir. Puedes borrarlas en «Fuentes y configuración».

## Errores habituales

| Mensaje | Causa probable |
|---|---|
| «La Riot API rechazó la clave» | Clave caducada (24 h) o mal copiada (401/403) |
| «No se encontró el recurso» | Riot ID o etiqueta mal escritos, o servidor equivocado (404) |
| «Límite de peticiones alcanzado» | Demasiadas peticiones seguidas (429); espera los segundos indicados |
| «No se pudo conectar» | Sin conexión a Internet |

## Enrutamiento

Para `match-v5` se usa la región de enrutamiento que corresponde a tu servidor:
- **americas**: LAN, LAS, NA, BR
- **europe**: EUW, EUNE, TR, RU
- **asia**: KR, JP
- **sea**: OCE, PH, SG, TH, TW, VN

`account-v1` solo ofrece americas, asia y europe, y permite consultar cualquier cuenta desde cualquiera de ellas. Para los servidores de sea se usa asia.

La documentación de Riot lista las plataformas y las regiones, pero no la tabla de correspondencia entre ellas. La agrupación de arriba es la convención habitual. Si una consulta falla con tu servidor, avísame.
