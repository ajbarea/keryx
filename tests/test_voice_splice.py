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
