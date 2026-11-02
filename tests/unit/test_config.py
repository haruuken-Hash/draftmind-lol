from draftmind.app.config import load_settings


def test_demo_mode_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("RIOT_API_KEY", raising=False)
    monkeypatch.setenv("DRAFTMIND_DATA_DIR", str(tmp_path))
    settings = load_settings(env_file=tmp_path / "no-existe.env")
    assert settings.demo_mode
    assert settings.data_dir == tmp_path


def test_api_key_is_hidden_from_repr(tmp_path, monkeypatch):
    monkeypatch.setenv("RIOT_API_KEY", "RGAPI-valor-de-prueba")
    settings = load_settings(env_file=tmp_path / "no-existe.env")
    assert not settings.demo_mode
    assert "RGAPI" not in repr(settings)
