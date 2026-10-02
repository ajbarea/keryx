from keryx.text import clean_for_speech, first_sentences, split_sentences


def test_drops_fenced_code_blocks():
    md = "Before.\n```python\nprint('hi')\n```\nAfter."
    assert clean_for_speech(md) == "Before. After."


def test_drops_tables_and_rules():
    md = "Results:\n| a | b |\n|---|---|\n| 1 | 2 |\n---\nDone."
    assert clean_for_speech(md) == "Results: Done."


def test_drops_headings_keeps_body():
    assert clean_for_speech("## Status\nAll green.") == "All green."


def test_strips_emphasis_and_inline_code():
    assert clean_for_speech("**Fixed** the `parser` *now*.") == "Fixed the parser now."


def test_keeps_snake_case_and_glob_text():
    assert clean_for_speech("Set max_tokens on *.py files.") == "Set max_tokens on *.py files."


def test_links_keep_label_and_bare_urls_become_a_link():
    md = "See [the docs](https://x.y/z) and https://example.com/a?b=1 for more."
    assert clean_for_speech(md) == "See the docs and a link for more."


def test_paths_reduce_to_file_name():
    md = "Edited `src/keryx/text.py:42` and /home/aj/notes/todo.md today."
    assert clean_for_speech(md) == "Edited text.py and todo.md today."


def test_bullets_become_sentences():
    md = "Two things:\n- tests pass\n- lint is clean\n1. ship it"
    assert clean_for_speech(md) == "Two things: tests pass. lint is clean. ship it."


def test_status_emoji_dropped():
    assert clean_for_speech("✅ merged, 📋 docs pending") == "merged, docs pending"


def test_blockquote_marker_dropped():
    assert clean_for_speech("> quoted line") == "quoted line"


def test_empty_and_code_only_give_empty():
    assert clean_for_speech("") == ""
    assert clean_for_speech("```\nx = 1\n```") == ""


def test_split_sentences():
    assert split_sentences("One. Two? Three! Four") == ["One.", "Two?", "Three!", "Four"]


def test_split_keeps_decimals_and_file_names():
    assert split_sentences("It took 0.2s in text.py. Next.") == [
        "It took 0.2s in text.py.",
        "Next.",
    ]


def test_first_sentences_respects_limit():
    text = "Short one. " + "word " * 60 + "end. Third."
    assert first_sentences(text, max_chars=40) == "Short one."


def test_first_sentences_truncates_a_single_long_sentence_on_a_word():
    out = first_sentences("alpha beta gamma delta epsilon", max_chars=17)
    assert out == "alpha beta gamma"
