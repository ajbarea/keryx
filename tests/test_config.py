import json

import pytest

from keryx.config import Config, config_dir, set_stored


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


def test_duck_apps_come_from_a_comma_separated_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("KERYX_DUCK_APPS", "Spotify, chrome ,")
    assert Config.load().duck_apps == ["Spotify", "chrome"]


def test_ducking_defaults_to_spotify_at_a_quarter(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("KERYX_DUCK_APPS", raising=False)
    cfg = Config.load()
    assert (cfg.duck_apps, cfg.duck_ratio) == (["Spotify"], 0.25)


@pytest.mark.parametrize(
    ("field", "bad"),
    [("duck_apps", "Spotify"), ("duck_apps", [1, 2]), ("duck_ratio", "half"), ("enabled", "yes")],
)
def test_a_value_of_the_wrong_type_falls_back_to_the_default(tmp_path, monkeypatch, field, bad):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "keryx").mkdir(exist_ok=True)
    (tmp_path / "keryx" / "config.json").write_text(json.dumps({field: bad}))
    assert getattr(Config.load(env=False), field) == getattr(Config(), field)


def test_a_whole_number_speed_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "keryx").mkdir(exist_ok=True)
    (tmp_path / "keryx" / "config.json").write_text('{"speed": 1, "duck_ratio": 0}')
    cfg = Config.load(env=False)
    assert (cfg.speed, cfg.duck_ratio) == (1, 0)


def test_an_env_override_follows_the_defaults_type_not_the_files(monkeypatch):
    config_dir().mkdir(parents=True)
    (config_dir() / "config.json").write_text('{"speed": 1}')
    monkeypatch.setenv("KERYX_SPEED", "1.3")
    assert Config.load().speed == 1.3


@pytest.mark.parametrize("text", ["[1, 2]", '"text"', "null", "42", "{broken", ""])
def test_a_config_file_that_is_not_an_object_is_ignored(text):
    config_dir().mkdir(parents=True)
    (config_dir() / "config.json").write_text(text)
    assert Config.load() == Config()


def test_a_config_file_that_is_not_text_is_ignored():
    config_dir().mkdir(parents=True)
    (config_dir() / "config.json").write_bytes(b"\xff\xfe\x00")
    assert Config.load() == Config()


def test_set_stored_writes_only_what_it_is_given():
    config_dir().mkdir(parents=True)
    (config_dir() / "config.json").write_text('{"voice": "am_adam"}')
    set_stored(enabled=False)
    assert json.loads((config_dir() / "config.json").read_text()) == {
        "voice": "am_adam",
        "enabled": False,
    }


def test_set_stored_keeps_a_file_it_cannot_read_beside_the_new_one():
    config_dir().mkdir(parents=True)
    (config_dir() / "config.json").write_text("{broken")
    set_stored(enabled=False)
    assert json.loads((config_dir() / "config.json").read_text()) == {"enabled": False}
    assert (config_dir() / "config.json.bad").read_text() == "{broken"


def test_set_stored_does_not_move_an_empty_object_with_whitespace():
    config_dir().mkdir(parents=True)
    (config_dir() / "config.json").write_text("{ \n}\n")
    set_stored(enabled=False)
    assert not (config_dir() / "config.json.bad").exists()


def test_set_stored_survives_a_file_it_may_not_read():
    import os

    if os.geteuid() == 0:
        pytest.skip("root reads anything")
    config_dir().mkdir(parents=True)
    path = config_dir() / "config.json"
    path.write_text('{"voice": "am_adam"}')
    path.chmod(0o000)
    set_stored(enabled=False)
    assert json.loads(path.read_text()) == {"enabled": False}
    assert (config_dir() / "config.json.bad").exists()
