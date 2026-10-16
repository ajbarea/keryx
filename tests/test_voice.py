from keryx.voice import default_voice
from keryx.voices import POOL


def test_a_real_kokoro_voice_is_kept():
    assert default_voice("bf_emma", {"af_heart", "bf_emma", "am_puck"}) == "bf_emma"


def test_a_typo_or_missing_voice_falls_back_to_the_pool_lead():
    assert default_voice("af_tpyo", {"af_heart", "bf_emma"}) == POOL[0]


def test_a_voice_removed_from_kokoro_falls_back():
    # If Kokoro lacked af_nicole, the default-synth path must fall back, not fail.
    assert default_voice("af_nicole", {"af_heart", "af_bella"}) == POOL[0]
