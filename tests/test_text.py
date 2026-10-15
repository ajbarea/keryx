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


def test_slashed_prose_and_dates_are_not_paths():
    text = "Tests pass on client/server and input/output, due 10/01/2026, over TCP/IP and/or UDP."
    assert clean_for_speech(text) == text


def test_rooted_paths_shrink_even_without_an_extension():
    assert clean_for_speech("See ./scripts/run and ~/notes/todo") == "See run and todo"


def test_commit_shas_become_a_commit():
    assert clean_for_speech("CI is green on 481803e.") == "CI is green on a commit."
    assert clean_for_speech("Merged `e1b0371` to main.") == "Merged a commit to main."
    sha40 = "0123456789abcdef0123456789abcdef01234567"
    assert clean_for_speech(f"Tag {sha40} built.") == "Tag a commit built."


def test_plain_numbers_and_hex_words_are_left_alone():
    assert clean_for_speech("All 1234567 tests pass.") == "All 1234567 tests pass."
    assert clean_for_speech("The deadbed cafe.") == "The deadbed cafe."  # no digit, not a sha
    assert clean_for_speech("Port 8080 is up.") == "Port 8080 is up."


def test_a_sha_inside_an_identifier_is_not_touched():
    assert clean_for_speech("Call x481803e now.") == "Call x481803e now."


def test_hash_number_reads_as_number_not_hash():
    assert clean_for_speech("Closed #85 today.") == "Closed number 85 today."
    assert clean_for_speech("See `#412`.") == "See number 412."


def test_a_labelled_ticket_keeps_its_label_and_drops_the_hash():
    assert clean_for_speech("Merged PR #85.") == "Merged PR 85."
    assert clean_for_speech("Opened issue #12 for it.") == "Opened issue 12 for it."


def test_an_uppercase_prefixed_hex_is_not_touched():
    assert clean_for_speech("Var X481803e holds it.") == "Var X481803e holds it."


def test_a_hex_segment_inside_a_path_collapses_with_the_path():
    assert clean_for_speech("See /var/cache/a1b2c3d4/log.txt here.") == "See log.txt here."


def test_a_hashed_asset_name_is_not_called_a_commit():
    assert clean_for_speech("Built chunk-a1b2c3d4.js now.") == "Built chunk-a1b2c3d4.js now."
