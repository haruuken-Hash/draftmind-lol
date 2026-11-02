"""Genera partidas FICTICIAS con el formato de match-v5 para el modo demostración.

Uso:  .venv\\Scripts\\python.exe tools\\generate_demo_matches.py

Los valores son inventados (semilla fija, siempre el mismo resultado) y el
archivo se marca con "demo": true. Solo sirven para probar la interfaz sin
API key; no representan partidas reales de nadie.
"""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "draftmind" / "resources" / "demo" / "matches_demo.json"
PUUID = "DEMO-PUUID-JUGADOR"
ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
POOL = {
    "TOP": ["Malphite", "Garen", "Darius", "Renekton", "Ornn"],
    "JUNGLE": ["Amumu", "Sejuani", "JarvanIV", "LeeSin", "MasterYi"],
    "MIDDLE": ["Ahri", "Orianna", "Lux", "Zed", "Kassadin"],
    "BOTTOM": ["Jinx", "Ashe", "Ezreal", "Caitlyn", "Vayne"],
    "UTILITY": ["Leona", "Thresh", "Janna", "Lulu", "Nautilus"],
}
MY_GAMES = ["TOP", "TOP", "MIDDLE", "TOP", "MIDDLE", "TOP", "TOP", "MIDDLE", "TOP", "TOP", "MIDDLE", "TOP", "TOP", "MIDDLE"]
ITEMS = {"TOP": [3047, 3075, 3065, 3053], "MIDDLE": [3020, 3089, 3157, 3135], "default": [3006, 3031, 3072, 3094]}
KEYSTONES = {"TOP": 8437, "MIDDLE": 8112, "default": 8008}


def participant(rng, puuid, champion, role, team_id, win, skill, minutes):
    cs_rate = {"UTILITY": 1.2, "JUNGLE": 5.5}.get(role, 6.0) * skill
    kills = rng.randint(0, 9)
    return {
        "puuid": puuid, "championName": champion, "teamId": team_id, "teamPosition": role, "win": win,
        "kills": kills, "deaths": rng.randint(1, 9), "assists": rng.randint(1, 14),
        "totalMinionsKilled": int(minutes * cs_rate * rng.uniform(0.85, 1.1)) if role != "JUNGLE" else int(minutes * 1.2),
        "neutralMinionsKilled": int(minutes * 4.3) if role == "JUNGLE" else rng.randint(0, 8),
        "goldEarned": int(minutes * rng.uniform(330, 450)), "visionScore": int(minutes * rng.uniform(0.5, 1.6)),
        "totalDamageDealtToChampions": int(minutes * rng.uniform(450, 950)),
        "totalDamageTaken": int(minutes * rng.uniform(500, 1100)),
        **{f"item{i}": v for i, v in enumerate(ITEMS.get(role, ITEMS["default"]) + [0, 0, 3340])},
        "summoner1Id": 4, "summoner2Id": 11 if role == "JUNGLE" else (12 if role == "TOP" else 14),
        "perks": {"styles": [
            {"description": "primaryStyle", "style": 8400,
             "selections": [{"perk": KEYSTONES.get(role, KEYSTONES["default"])}]},
            {"description": "subStyle", "style": 8300, "selections": []},
        ]},
    }


def main():
    rng = random.Random(2026)
    start = datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc)
    matches = []
    for n, my_role in enumerate(MY_GAMES):
        played = start - timedelta(days=n * 1.7, hours=rng.randint(0, 5))
        minutes = rng.randint(22, 38)
        # Tendencia ficticia: las partidas recientes tienen algo más de CS.
        skill = 1.0 + (0.12 if n < 5 else 0.0)
        my_win = rng.random() < 0.55
        players = []
        for team_id, team_win in ((100, my_win), (200, not my_win)):
            used = set()
            for role in ROLES:
                if team_id == 100 and role == my_role:
                    champ = rng.choice(POOL[role][:3])
                    players.append(participant(rng, PUUID, champ, role, team_id, team_win, skill, minutes))
                    used.add(champ)
                    continue
                champ = rng.choice([c for c in POOL[role] if c not in used])
                used.add(champ)
                players.append(participant(rng, f"DEMO-{team_id}-{role}", champ, role, team_id, team_win, 1.0, minutes))
        created = int(played.timestamp() * 1000)
        matches.append({
            "metadata": {"matchId": f"DEMO_{9000 + n}"},
            "info": {
                "gameCreation": created, "gameDuration": minutes * 60,
                "gameEndTimestamp": created + minutes * 60_000, "gameVersion": "16.20.700.1234",
                "queueId": 420, "participants": players,
            },
        })
    OUT.write_text(json.dumps({
        "demo": True,
        "notes": "Partidas ficticias generadas por tools/generate_demo_matches.py. No son datos reales.",
        "puuid": PUUID, "game_name": "Jugador Demo", "tag_line": "DEMO", "platform": "LA1",
        "matches": matches,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(matches)} partidas escritas en {OUT}")


if __name__ == "__main__":
    main()
