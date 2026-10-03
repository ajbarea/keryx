import os
import time

from keryx.pronounce import Lexicon, apply, load, save

S = "\u02c8"  # IPA primary stress, which espeak writes before the stressed vowel


def test_whole_words_are_replaced_without_regard_to_case():
    words = {"ajsoftworks": "AJ soft works"}
    assert apply(words, "ajsoftworks: Done.") == "AJ soft works: Done."
    assert apply(words, "In AJSoftworks today.") == "In AJ soft works today."
    assert apply(words, "myajsoftworks2") == "myajsoftworks2"


def test_longer_words_win_over_their_prefixes():
    words = {"phalanx": "FALANKS", "phalanx-fl": "phalanx F L"}
    assert apply(words, "phalanx-fl and phalanx") == "phalanx F L and FALANKS"


def test_words_with_regex_characters_are_matched_literally():
    assert apply({"c++": "C plus plus"}, "I wrote c++ code.") == "I wrote C plus plus code."
    assert apply({"a.b": "A B"}, "axb") == "axb"


def test_no_words_leaves_text_alone():
    assert apply({}, "Same.") == "Same."


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "p.json"
    save({"b": "bee", "a": "ay"}, path)
    assert load(path) == {"a": "ay", "b": "bee"}
    assert not (tmp_path / "p.tmp").exists()


def test_a_malformed_file_reads_as_empty(tmp_path):
    path = tmp_path / "p.json"
    for content in ("[1]", "{nope", '{"a": 5, "": "x", "ok": "fine"}'):
        path.write_text(content)
        assert load(path) in ({}, {"ok": "fine"})
    assert load(tmp_path / "missing.json") == {}


def test_the_lexicon_rereads_a_changed_file(tmp_path):
    path = tmp_path / "p.json"
    lex = Lexicon(path)
    assert lex("keryx") == "keryx"
    save({"keryx": "KEH rix"}, path)
    assert lex("keryx") == "KEH rix"
    save({"keryx": "kerr ix"}, path)
    stamp = time.time_ns() + 10**9
    os.utime(path, ns=(stamp, stamp))  # a second write within the clock tick still counts
    assert lex("keryx") == "kerr ix"
    path.unlink()
    assert lex("keryx") == "keryx"


def test_case_mappings_that_change_length_do_not_crash():
    # Each of these used to raise KeyError when the matched text's case did not map back.
    assert apply({"\u0130stanbul": "X"}, "\u0130STANBUL") == "X"
    apply({"\u0130stanbul": "X"}, "istanbul")
    assert apply({"os": "oh ess"}, "o\u017f") == "oh ess"


def test_unreadable_files_raise_only_when_strict(tmp_path):
    import pytest

    path = tmp_path / "p.json"
    path.write_text('{"a": "b",}')
    assert load(path) == {}
    with pytest.raises(ValueError, match="fix or remove"):
        load(path, strict=True)


def test_a_slashed_saying_reaches_the_voice_as_marked_phonemes():
    words = {"techne": f"/t{S}exni/", "ajsoftworks": "AJ soft works"}
    assert apply(words, "techne, by ajsoftworks.") == f"⟦t{S}exni⟧, by AJ soft works."


def test_only_a_whole_slashed_saying_is_phonemes():
    from keryx.pronounce import phonemes

    assert phonemes(f" /t{S}exni/ ") == f"t{S}exni"
    assert phonemes("a/b/c") is None
    assert phonemes("TEK nee") is None
    assert phonemes("//") is None


def test_ascii_lookalikes_become_the_ipa_symbols_kokoro_knows():
    from keryx.pronounce import phonemes

    assert phonemes("/gɹiːk/") == "\u0261ɹiːk"
    assert phonemes("/k'ɛɹɪks/") == f"k{S}ɛɹɪks"
    assert phonemes("/ /") is None


def test_marks_in_a_reply_are_not_taken_for_phonemes():
    assert apply({}, "math ⟦x⟧") == "math x"
    assert apply({"techne": f"/t{S}exni/"}, "⟦x⟧ techne") == f"x ⟦t{S}exni⟧"
