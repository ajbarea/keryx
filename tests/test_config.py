import pytest

from keryx.config import Config, config_dir


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for key in ("KERYX_ENABLED", "KERYX_VOICE", "KERYX_SPEED", "KERYX_MODEL"):
        monkeypatch.delenv(key, raising=False)


def test_defaults_without_a_file():
    assert Config.load() == Config()


def test_round_trip():
    Config(voice="bm_george", speed=1.2).save()
    cfg = Config.load()
    assert (cfg.voice, cfg.speed) == ("bm_george", 1.2)


def test_unknown_keys_and_bad_json_are_ignored():
    config_dir().mkdir(parents=True)
    (config_dir() / "config.json").write_text('{"voice": "am_adam", "colour": "red"}')
    assert Config.load().voice == "am_adam"
    (config_dir() / "config.json").write_text("{broken")
    assert Config.load() == Config()


def test_env_overrides_file(monkeypatch):
    Config(voice="am_adam").save()
    monkeypatch.setenv("KERYX_VOICE", "bf_emma")
    monkeypatch.setenv("KERYX_SPEED", "1.3")
    monkeypatch.setenv("KERYX_ENABLED", "off")
    cfg = Config.load()
    assert (cfg.voice, cfg.speed, cfg.enabled) == ("bf_emma", 1.3, False)


def test_a_bad_env_value_keeps_the_default(monkeypatch):
    monkeypatch.setenv("KERYX_SPEED", "fast")
    assert Config.load().speed == Config().speed
