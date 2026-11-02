"""Convierte los resultados del análisis de draft en HTML para un QTextBrowser.

Es código puro (sin Qt), así que se puede probar sin abrir ventanas.
Cada valoración se expresa con texto ("Favorable", "Desfavorable"...) y no
solo con color.
"""

from html import escape

from draftmind.domain.enums import EvidenceKind
from draftmind.domain.models import CandidateAnalysis, DataSource, FactorResult, TeamProfile


def rating_text(f: FactorResult) -> str:
    if f.kind is EvidenceKind.INSUFFICIENT:
        return "Sin datos"
    if f.score > 0:
        return f"Favorable (+{f.score:.2f})"
    if f.score < 0:
        return f"Desfavorable ({f.score:.2f})"
    return "Neutro (0)"


def _list(items: list[str], empty: str) -> str:
    if not items:
        return f"<p><i>{escape(empty)}</i></p>"
    return "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"


def _team_html(title: str, team: TeamProfile) -> str:
    if not team.champion_ids:
        return f"<h3>{escape(title)}</h3><p><i>Sin campeones conocidos.</i></p>"
    return (
        f"<h3>{escape(title)}</h3>"
        f"<p>Daño: {team.physical_share:.0%} físico / {team.magic_share:.0%} mágico · "
        f"Iniciación {team.engage} · Desenganche {team.disengage} · Control {team.cc} · "
        f"Temprano {team.early} · Escalado {team.scaling} · Primera línea {team.frontline}</p>"
        "<p><b>Fortalezas probables (inferencia):</b></p>"
        + _list(team.strengths, "No se detectan fortalezas destacadas.")
        + "<p><b>Debilidades probables (inferencia):</b></p>"
        + _list(team.weaknesses, "No se detectan debilidades destacadas.")
    )


def _candidate_html(a: CandidateAnalysis) -> str:
    rows = "".join(
        f"<tr><td>{escape(f.label)}</td><td>{rating_text(f)}</td>"
        f"<td>{escape(f.kind.label)}</td><td>{escape(f.explanation)}</td></tr>"
        for f in a.factors
    )
    warnings = "".join(f"<p><b>Advertencia:</b> {escape(w)}</p>" for w in a.confidence.warnings)
    return (
        f"<h2>{escape(a.champion.name)}</h2>"
        f"<p><b>Puntuación orientativa:</b> {a.score:.0f}/100 · "
        f"<b>Confianza:</b> {a.confidence.level.label}</p>"
        f"<p><small>{escape(' '.join(a.confidence.reasons))}</small></p>"
        f"{warnings}"
        "<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
        "<tr><th>Criterio</th><th>Valoración</th><th>Tipo</th><th>Explicación</th></tr>"
        f"{rows}</table>"
        "<p><b>Ventajas:</b></p>" + _list(a.pros, "Ninguna destacable con los datos disponibles.")
        + "<p><b>Desventajas:</b></p>" + _list(a.cons, "Ninguna destacable con los datos disponibles.")
    )


def render_report(
    analyses: list[CandidateAnalysis],
    allies: TeamProfile,
    enemies: TeamProfile,
    sources: list[DataSource],
    heading: str,
) -> str:
    parts = [f"<h1>{escape(heading)}</h1>"]
    if len(analyses) > 1:
        rows = "".join(
            f"<tr><td>{escape(a.champion.name)}</td><td>{a.score:.0f}</td>"
            f"<td>{a.confidence.level.label}</td><td>{len(a.pros)}</td><td>{len(a.cons)}</td></tr>"
            for a in analyses
        )
        parts.append(
            "<h3>Comparación</h3>"
            "<table border='1' cellspacing='0' cellpadding='4'>"
            "<tr><th>Campeón</th><th>Puntuación</th><th>Confianza</th>"
            "<th>Ventajas</th><th>Desventajas</th></tr>"
            f"{rows}</table>"
            "<p><small>La puntuación resume los criterios cualitativos de abajo; "
            "no es un win rate ni una predicción del resultado.</small></p>"
        )
    if not analyses:
        parts.append("<p><i>No hay candidatos que analizar con los filtros actuales.</i></p>")
    parts.extend(_candidate_html(a) for a in analyses)
    parts.append("<hr>" + _team_html("Tu equipo", allies) + _team_html("Equipo enemigo", enemies))
    parts.append("<hr><h3>Fuentes</h3>")
    for s in sources:
        patch = s.patch or "sin parche asociado"
        parts.append(
            f"<p><b>{escape(s.name)}</b> ({escape(s.kind.label)}; {escape(patch)})<br>"
            f"{escape(s.notes or '')}</p>"
        )
    return "".join(parts)
