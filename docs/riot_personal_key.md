# Solicitar una clave personal de Riot

La clave de desarrollo se desactiva cada 24 horas. Para un proyecto propio como DraftMind, Riot ofrece la **clave personal** (*Personal API Key*). Es gratuita y se obtiene registrando el producto en el portal de desarrolladores.

Información comprobada en el portal el 1 de noviembre de 2026 ([docs/portal](https://developer.riotgames.com/docs/portal), [docs/lol](https://developer.riotgames.com/docs/lol) y [políticas generales](https://developer.riotgames.com/policies/general)).

## Qué dice Riot de la clave personal

- Es para productos «pensados solo para el desarrollador o una pequeña comunidad privada». Entre los ejemplos aceptados está explícitamente «proyectos personales para recopilar tus propias estadísticas».
- Límites: 20 peticiones por segundo y 100 cada 2 minutos, por región. Son los mismos que ya respeta DraftMind (`utils/rate_limiter.py`).
- **No se puede usar para una aplicación pública**, incluidas las versiones alfa o beta abiertas. DraftMind tiene que quedarse para tu uso personal; no repartas el ejecutable con tu clave.
- Riot exige «una descripción detallada del producto».
- **Caducidad:** la documentación dice que la clave de desarrollo se desactiva cada 24 horas, pero no dice nada sobre la caducidad de la personal. Confírmalo cuando te la aprueben.
- Si el producto usa la API del cliente (League Client API), como el draft en vivo, Riot pide que se lo indiques al registrarlo, **con los endpoints que usas y para qué**.

## Pasos

1. Entra en <https://developer.riotgames.com> con tu cuenta de Riot.
2. Lee las políticas: Riot da por hecho que las conoces.
3. Pulsa **«Register Product»** y elige **proyecto personal** (*Personal API Key*).
4. Rellena el formulario. Usa el texto de abajo: está en inglés porque el portal está en inglés. El formulario no se pudo ver sin iniciar sesión, así que adapta el texto a los campos que te pida.
5. Espera la revisión. La respuesta llega como mensaje en el propio portal.
6. Cuando te la aprueben, sustituye la clave en tu `.env`:

   ```
   RIOT_API_KEY=la-clave-nueva
   ```

   Después reinicia DraftMind. Nunca la pongas en el código ni la compartas.

## Texto para la solicitud

**Product name:** DraftMind LoL (personal)

**Product description:**

> DraftMind LoL is a personal, non-commercial Windows desktop app that I am building to study my own League of Legends games and learn programming. It is used only by me and will not be distributed publicly.
>
> What it does:
> - Shows my own match history and aggregate stats (KDA, CS/min, vision, a per-match performance score computed only among the 10 players of each match), my ranked entries and my champion mastery.
> - Post-game analysis of my own matches, including the laning phase (gold/CS/XP difference at minutes 5, 10 and 15 from the official match timeline).
> - A draft study tool: during champion select it reads my own client's champion select session (read-only) and shows composition notes, possible picks with their reasons, ban ideas and example builds, always presenting several options with the evidence behind each one. It never picks, bans or performs any action in the client.
>
> Riot API endpoints used (only for my own account):
> - account-v1: /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine} (once, to get my PUUID)
> - match-v5: /lol/match/v5/matches/by-puuid/{puuid}/ids, /lol/match/v5/matches/{matchId}, /lol/match/v5/matches/{matchId}/timeline
> - league-v4: /lol/league/v4/entries/by-puuid/{puuid}
> - champion-mastery-v4: /lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top
>
> Results are cached locally in SQLite, so each match is requested only once. The app respects the rate limits and Retry-After on 429 responses.
>
> League Client API (opt-in, read-only, GET requests to 127.0.0.1 only):
> - GET /lol-gameflow/v1/gameflow-phase: to know whether I am in champion select, in game or at the end of game.
> - GET /lol-champ-select/v1/session: to show the champions and bans already visible to me in champion select. Player names are not read or displayed.
>
> Compliance:
> - No overlays, no timers and no information during the game: the app stops updating when the game starts, and resumes after it ends to download that match.
> - No memory reading, no automation, no hidden information, no MMR estimates.
> - The API key is stored in a local .env file and is never included in the code or in the executable.
> - The app shows Riot's legal disclaimer ("DraftMind LoL isn't endorsed by Riot Games…").

## Si la rechazan

Riot puede pedir más detalle o rechazar la solicitud. En ese caso, DraftMind sigue funcionando con la clave de desarrollo: tendrás que renovarla cada 24 horas en el portal.
