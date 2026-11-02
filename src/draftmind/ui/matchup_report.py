"""HTML del enfrentamiento por fases y de los gankeos (pantalla «Draft»)."""

from html import escape

from draftmind.analysis.lane_matchup import GankDanger, GankOption, LaneMatchup
from draftmind.ui import theme

GANK_COLORS = {"Buen objetivo": theme.WIN, "Posible": theme.WARNING, "Difícil": theme.LOSS}
DANGER_COLORS = {"alto": theme.LOSS, "medio": theme.WARNING, "bajo": theme.WIN}


def _small(text: str) -> str:
    return f"<span style='color:{theme.MUTED}; font-size:8pt'>{text}</span>"


def _edge_chip(edge: int, enemy_name: str) -> str:
    if edge > 0:
        return f"<b style='color:{theme.WIN}'>Ventaja tuya</b>"
    if edge < 0:
        return f"<b style='color:{theme.LOSS}'>Ventaja de {escape(enemy_name)}</b>"
    return f"<b style='color:{theme.MUTED}'>Parejo</b>"


def matchup_html(m: LaneMatchup, names: dict[str, str], deduced: bool, tips: list[str] | None) -> str:
    mine, enemy = names.get(m.my_id, m.my_id), names.get(m.enemy_id, m.enemy_id)
    parts = [f"<b>{escape(mine)}</b> contra <b>{escape(enemy)}</b>"]
    if deduced:
        parts.append(_small(" (rival deducido de su perfil: indica su posición en su casilla si no es así)"))
    parts.append(f"<p style='margin:6px 0'>{escape(m.summary)}</p>")

    rows = []
    for p in m.phases:
        kinds = " + ".join(dict.fromkeys(k.label for k in p.kinds))
        reasons = "<br>".join(escape(r) for r in p.reasons)
        rows.append(
            f"<tr><td style='padding:4px 10px 4px 0; white-space:nowrap'><b>Nivel {p.levels}</b><br>"
            f"{_small(escape(p.title))}</td>"
            f"<td style='padding:4px 10px 4px 0; white-space:nowrap'>{_edge_chip(p.edge, enemy)}</td>"
            f"<td style='padding:4px 0'>{reasons}<br>{_small(escape(kinds))}</td></tr>"
        )
    parts.append("<table cellspacing='0'>" + "".join(rows) + "</table>")

    if m.durability:
        cells = "".join(
            f"<td style='padding:0 10px 0 0'>Nv {r.level}: {r.my_hp:.0f} / {r.enemy_hp:.0f} vida · "
            f"{r.my_armor:.0f} / {r.enemy_armor:.0f} armadura</td>"
            for r in m.durability
        )
        parts.append(f"<p style='margin:6px 0 0 0'><b>Aguante base</b> {_small('(tú / rival, dato oficial, sin objetos)')}"
                     f"</p><table><tr>{cells}</tr></table>")

    parts.append(f"<p style='margin:6px 0 0 0'><b>Tu historial</b> {_small(escape(m.history.kind.label))}<br>"
                 f"{escape(m.history.text)}</p>")
    if tips:
        items = "".join(f"<li>{escape(t)}</li>" for t in tips[:3])
        parts.append(f"<p style='margin:6px 0 0 0'><b>Cómo jugar contra {escape(enemy)}</b> "
                     f"{_small('(consejos oficiales de Riot)')}</p><ul style='margin:2px 0'>{items}</ul>")
    note = ("Ventaja probable a partir de perfiles y estadísticas base oficiales. No incluye habilidades, runas ni "
            "objetos: es una guía para planificar, no un resultado seguro.")
    if m.estimated_profiles:
        note += " Algún perfil es estimado automáticamente: tómalo con más cautela."
    parts.append(f"<p style='margin:6px 0 0 0'>{_small(note)}</p>")
    return "".join(parts)


def ganks_html(options: list[GankOption], names: dict[str, str]) -> str:
    if not options:
        return _small("Indica las posiciones del equipo rival para valorar los gankeos.")
    rows = []
    for o in options:
        targets = " + ".join(escape(names.get(c, c)) for c in o.enemy_ids)
        reasons = "<br>".join(escape(r) for r in o.reasons)
        rows.append(
            f"<tr><td style='padding:4px 10px 4px 0; white-space:nowrap'><b>{escape(o.lane.label)}</b><br>"
            f"{_small(targets)}</td>"
            f"<td style='padding:4px 10px 4px 0; white-space:nowrap'>"
            f"<b style='color:{GANK_COLORS[o.verdict]}'>{o.verdict}</b></td>"
            f"<td style='padding:4px 0'>{reasons}</td></tr>"
        )
    return ("<table cellspacing='0'>" + "".join(rows) + "</table>"
            + _small("Inferencia a partir de los perfiles de los campeones de cada línea. Los perfiles no miden "
                     "toda la movilidad (saltos, destellos de habilidades): revisa sus habilidades en «Campeones». "
                     "Lo que pase en la partida (vida, oleadas, visión) manda más que esta valoración previa."))


def danger_html(danger: GankDanger, names: dict[str, str]) -> str:
    name = escape(names.get(danger.jungler_id, danger.jungler_id))
    reasons = "<br>".join(escape(r) for r in danger.reasons)
    return (f"<b>Riesgo de gankeo de {name}:</b> "
            f"<b style='color:{DANGER_COLORS[danger.level]}'>{danger.level}</b><br>{reasons}<br>"
            + _small("Inferencia a partir de los perfiles."))
