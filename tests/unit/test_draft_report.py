from draftmind.domain.enums import Role
from draftmind.domain.models import DraftPick, DraftState
from draftmind.ui.draft_report import render_report


def test_report_contains_text_ratings_and_sources(analyzer, dataset):
    draft = DraftState(my_role=Role.MIDDLE, enemies=[DraftPick(champion_id="Zed", role=Role.MIDDLE)])
    analyses = [analyzer.analyze_candidate(draft, i) for i in ("Ahri", "Orianna")]
    allies, enemies = analyzer.compositions(draft)
    html = render_report(analyses, allies, enemies, [dataset.source], "Prueba")

    assert "Comparación" in html                # Tabla comparativa con 2+ candidatos.
    assert "Sin datos" in html                  # Factores sin evidencia, en texto.
    assert "Confianza:</b> Baja" in html
    assert "Advertencia:" in html
    assert "sin parche asociado" in html
    assert "no es un win rate" in html


def test_report_escapes_html(analyzer, dataset):
    allies, enemies = analyzer.compositions(DraftState())
    html = render_report([], allies, enemies, [dataset.source], "<script>")
    assert "<script>" not in html
