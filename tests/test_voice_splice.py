from keryx.voice import splice

S = "\u02c8"  # IPA primary stress, which espeak writes before the stressed vowel


def fake_phonemize(text: str) -> str:
    return f"<{text.strip()}>"


def test_plain_text_keeps_kokoros_own_path():
    assert splice("Nothing marked here.", fake_phonemize) is None


def test_marked_words_keep_their_phonemes_and_the_rest_is_phonemized():
    assert splice(f"This is ⟦t{S}exni⟧, by AJ.", fake_phonemize) == f"<This is> t{S}exni <, by AJ.>"


def test_punctuation_after_a_marked_word_attaches_to_it():
    assert splice(f"⟦t{S}exni⟧.", lambda t: t.strip()) == f"t{S}exni."
    assert (
        splice(f"Hi ⟦k{S}iɾiks⟧ and ⟦f{S}aɾos⟧!", lambda t: t.strip())
        == f"Hi k{S}iɾiks and f{S}aɾos!"
    )


def test_a_possessive_joins_the_marked_word_and_brackets_hug_it():
    assert splice(f"⟦t{S}exni⟧'s tools", lambda x: x.strip()) == f"t{S}exniz tools"
    assert splice(f"(⟦t{S}exni⟧) and “⟦t{S}exni⟧”.", lambda x: x.strip()) == (
        f"(t{S}exni) and “t{S}exni”."
    )


def test_kokoro_gets_phonemes_only_when_something_is_marked():
    import numpy as np

    from keryx.voice import KokoroVoice
    from keryx.voices import VoiceSpec

    calls = []

    class FakeKokoro:
        class tokenizer:  # mirrors Kokoro's attribute
            @staticmethod
            def phonemize(text, lang):
                return f"<{text.strip()}>"

        def create(self, text, **kw):
            calls.append((text, kw["is_phonemes"]))
            return np.zeros(2400, dtype=np.float32), 24000

    voice = KokoroVoice.__new__(KokoroVoice)
    voice._kokoro = FakeKokoro()
    voice.voice, voice.speed, voice.loudness = VoiceSpec(("af_heart",)), 1.0, -16.0
    voice._styles = {voice.voice: np.zeros(256, dtype=np.float32)}  # style() reads the cache
    voice.synth("Plain words.")
    voice.synth(f"Say ⟦t{S}exni⟧.")
    assert calls == [("Plain words.", False), (f"<Say> t{S}exni <.>", True)]


def test_the_possessive_follows_the_last_sound():
    from keryx.voice import possessive

    assert (possessive(f"t{S}exni"), possessive("bæʃ"), possessive("pˈaɪtɛst")) == ("z", "ɪz", "s")
