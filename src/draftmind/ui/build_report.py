"""HTML de las recomendaciones de build (compartido por «Runas y builds» y «Draft»)."""

from html import escape
from pathlib import Path

from draftmind.analysis.build_analyzer import BuildAdvice
from draftmind.app.bootstrap import AppContext
from draftmind.ui import theme


def img_tag(ctx: AppContext, relative: str | None, size: int = 26) -> str:
    path = ctx.catalogs.client.cached_image(relative) if relative else None
    if path is None:
        return ""
    return f"<img src='{Path(path).as_posix()}' width='{size}' height='{size}'> "


def item_img(ctx: AppContext, item_id: str | int, size: int = 26) -> str:
    data = ctx.game_data
    return img_tag(ctx, f"{data.version}/img/item/{item_id}.png", size) if data else ""


def build_advice_html(ctx: AppContext, advice: BuildAdvice, matches_are_demo: bool, compact: bool = False) -> str:
    """Recomendaciones de objetos, runas y hechizos. `compact` resume para el panel del draft."""
    data = ctx.game_data
    muted = theme.MUTED
    heading = "h4" if compact else "h3"
    parts = []

    # Objetos situacionales según la composición enemiga.
    parts.append(f"<{heading}>Objetos según el equipo rival</{heading}>")
    if advice.needs:
        for need in advice.needs:
            if compact:
                items = " ".join(f"{item_img(ctx, i.id, 24)}{escape(i.name)}" for i in need.items[:3])
                parts.append(f"<p><b>{escape(need.title)}</b> <i style='color:{muted}'>[{need.kind.label}]</i> — "
                             f"{escape(need.reason)}<br>{items}</p>")
                continue
            items = "".join(
                f"<div>{item_img(ctx, i.id)}<b>{escape(i.name)}</b> · {i.total_gold} de oro — "
                f"<span style='color:{muted}'>{escape(i.plaintext)}</span></div>"
                for i in need.items
            ) or f"<div style='color:{muted}'>No se encontraron objetos con esas características.</div>"
            parts.append(f"<p><b>{escape(need.title)}</b> <i>[{need.kind.label}]</i><br>{escape(need.reason)}</p>"
                         f"{items}<p style='color:{muted}'>Ejemplos según etiquetas oficiales; no son "
                         "la única opción ni necesariamente la mejor.</p>")
    else:
        parts.append(f"<p style='color:{muted}'>Sin necesidades situacionales con los rivales conocidos.</p>")

    # Lo que tú sueles construir.
    if advice.frequent_items:
        demo = " (partidas FICTICIAS de demostración)" if matches_are_demo else ""
        if compact:
            items = " ".join(f"{item_img(ctx, f.item_id, 24)}{escape(f.name)} ({f.games})"
                             for f in advice.frequent_items[:5])
            parts.append(f"<{heading}>Lo que sueles construir</{heading}><p>{items}<br>"
                         f"<span style='color:{muted}'>Frecuencia en tus {advice.personal_games} partidas{demo}; "
                         "no mide eficacia.</span></p>")
        else:
            parts.append(f"<{heading}>Tus configuraciones frecuentes ({advice.personal_games} partidas)</{heading}>")
            parts.append(f"<p style='color:{muted}'>Estadística observada en tus partidas{demo}. "
                         "Frecuencia de uso, no eficacia.</p>")
            for f in advice.frequent_items:
                parts.append(f"<div>{item_img(ctx, f.item_id)}<b>{escape(f.name)}</b>: en {f.games} partidas "
                             f"({f.wins} victorias)</div>")
        for name, games, wins in advice.frequent_keystones[: (1 if compact else 3)]:
            parts.append(f"<div>Runa clave que más usas: <b>{escape(name)}</b> ({games} partidas, {wins} victorias)</div>")

    # Runas: árboles orientativos con sus runas clave oficiales.
    parts.append(f"<{heading}>Runas</{heading}>")
    for rune in advice.runes[: (1 if compact else 3)]:
        keystones = (" ".join(f"{img_tag(ctx, 'img/' + k.icon, 22)}{escape(k.name)}" for k in rune.path.keystones)
                     if compact else "".join(
                         f"<div>{img_tag(ctx, 'img/' + k.icon, 24)}<b>{escape(k.name)}</b>: "
                         f"<span style='color:{muted}'>{escape(k.short_desc)}</span></div>"
                         for k in rune.path.keystones))
        parts.append(f"<p>{img_tag(ctx, 'img/' + rune.path.icon, 22)}<b>{escape(rune.path.name)}</b> "
                     f"<i style='color:{muted}'>[{rune.kind.label}]</i><br>{escape(rune.reason)}</p>"
                     + (f"<p>{keystones}</p>" if compact else keystones))
    if not advice.runes:
        parts.append(f"<p style='color:{muted}'>Sin orientación de runas para este campeón.</p>")

    # Hechizos.
    parts.append(f"<{heading}>Hechizos de invocador</{heading}>")
    spells = data.spells if data else []
    spell_html = []
    for s in advice.spells:
        image = next((sp.image_file for sp in spells if sp.id == s.spell_id), None)
        img = img_tag(ctx, f"{data.version}/img/spell/{image}", 22) if image and data else ""
        spell_html.append(f"{img}<b>{escape(s.name)}</b>" if compact else
                          f"<div>{img}<b>{escape(s.name)}</b>: {escape(s.reason)} <i>[Sugerencia educativa]</i></div>")
    parts.append(f"<p>{' · '.join(spell_html)}</p>" if compact else "".join(spell_html))

    if not compact:
        parts.append("".join(f"<p style='color:{muted}'>Nota: {escape(n)}</p>" for n in advice.notes))
    return "".join(parts)
