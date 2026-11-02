import os

import pytest

# Qt sin ventana visible: permite probar la interfaz en segundo plano.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from draftmind.analysis.draft_analyzer import DraftAnalyzer  # noqa: E402
from draftmind.data.demo_data import load_demo_dataset  # noqa: E402


@pytest.fixture(scope="session")
def dataset():
    return load_demo_dataset()


@pytest.fixture
def analyzer(dataset):
    return DraftAnalyzer(dataset.champions, dataset.source)
