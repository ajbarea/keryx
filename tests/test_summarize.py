import urllib.error

from keryx.summarize import DIRECT_MAX_CHARS, SPOKEN_MAX_CHARS, spoken_line


class FakeClient:
    def __init__(self, reply="I fixed it. Please review the PR.", exc=None):
        self.reply = reply
        self.exc = exc
        self.prompts: list[str] = []

    def generate(self, prompt, system):
        self.prompts.append(prompt)
        if self.exc:
            raise self.exc
        return self.reply


LONG = "I changed the parser. " * 20


def test_short_reply_is_spoken_directly_without_the_model():
    client = FakeClient()
    assert spoken_line("**Done.** Tests pass.", client) == "Done. Tests pass."
    assert client.prompts == []


def test_long_reply_goes_through_the_model_with_cleaned_text():
    client = FakeClient()
    assert spoken_line(LONG + "\n```\ncode()\n```", client) == "I fixed it. Please review the PR."
    assert "code()" not in client.prompts[0]
    assert len(LONG) > DIRECT_MAX_CHARS


def test_model_output_is_cleaned_and_unquoted():
    client = FakeClient(reply='"**I fixed** `src/a/b.py`."')
    assert spoken_line(LONG, client) == "I fixed b.py."


def test_model_down_falls_back_to_opening_sentences():
    client = FakeClient(exc=urllib.error.URLError("refused"))
    out = spoken_line(LONG, client)
    assert out.startswith("I changed the parser.")
    assert len(out) <= SPOKEN_MAX_CHARS


def test_empty_model_output_falls_back():
    assert spoken_line(LONG, FakeClient(reply="   ")).startswith("I changed the parser.")


def test_no_client_falls_back():
    assert spoken_line(LONG, None).startswith("I changed the parser.")


def test_code_only_reply_is_silent():
    assert spoken_line("```\nx = 1\n```", FakeClient()) == ""
