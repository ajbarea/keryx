import re


def version() -> str:
    """The installed keryx version; looked up on demand, since hooks import this package."""
    from importlib.metadata import version as installed

    return installed("keryx")


_STAGES = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
_SUFFIX = re.compile(
    r"(?:[-_.]?(?P<stage>a|alpha|b|beta|c|rc|pre|preview)[-_.]?(?P<pre>\d*))?"
    r"(?:[-_.]?(?:post|rev|r)[-_.]?(?P<post>\d*)|-(?P<implicit_post>\d+))?"
    r"(?:[-_.]?(?P<dev>dev)[-_.]?(?P<devn>\d*))?"
)


def _order(text: object) -> tuple:
    """A PEP 440 sort key for a version such as 0.5.1, 0.5.1rc10, 0.5.1.post1.dev2 or
    0.5.1-1; case is ignored and so is a local part after `+`. ValueError if unreadable."""
    found = re.fullmatch(r"(\d+(?:\.\d+)*)([^+]*)(?:\+.*)?", str(text).strip().lower())
    suffix = _SUFFIX.fullmatch(found[2]) if found else None
    if found is None or suffix is None:
        raise ValueError(text)
    numbers = [int(n) for n in found[1].split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()  # 0.5 is 0.5.0
    post = suffix["post"] if suffix["post"] is not None else suffix["implicit_post"]
    if suffix["stage"]:
        pre = (0, _STAGES[suffix["stage"]], int(suffix["pre"] or 0))
    elif suffix["dev"] and post is None:
        pre = (-1,)  # 1.0.dev1 comes before 1.0a1
    else:
        pre = (1,)
    post_key = (int(post or 0),) if post is not None else (-1,)
    dev_key = (0, int(suffix["devn"] or 0)) if suffix["dev"] else (1,)
    return (tuple(numbers), pre, post_key, dev_key)


def older(theirs: object, ours: str) -> bool:
    """Whether version `theirs` predates `ours`; a missing or unreadable `theirs` counts as
    older. An unreadable `ours` says nothing, so nothing counts as older than it."""
    try:
        mine = _order(ours)
    except ValueError:
        return False
    try:
        return _order(theirs) < mine
    except ValueError:
        return True
