import re


def version() -> str:
    """The installed keryx version; looked up on demand, since hooks import this package."""
    from importlib.metadata import version as installed

    return installed("keryx")


_STAGES = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
_PRE = re.compile(r"[-_.]?(a|alpha|b|beta|c|rc|pre|preview)[-_.]?(\d*)")
_POST = re.compile(r"[-_.]?(?:post|rev|r)[-_.]?(\d*)")
_DEV = re.compile(r"[-_.]?dev[-_.]?(\d*)")


def _order(text: object) -> tuple:
    """A sort key for a version such as 0.5.1, 0.5.1rc10 or 0.5.1.post1; a local part after
    `+` is ignored. ValueError if unreadable."""
    found = re.fullmatch(r"(\d+(?:\.\d+)*)([^+]*)(?:\+.*)?", str(text).strip())
    if found is None:
        raise ValueError(text)
    numbers = [int(n) for n in found[1].split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()  # 0.5 is 0.5.0
    rest = found[2]
    if not rest:
        tail = (1, 0, 0)
    elif m := _DEV.fullmatch(rest):
        tail = (-1, 0, int(m[1] or 0))
    elif m := _PRE.fullmatch(rest):
        tail = (0, _STAGES[m[1]], int(m[2] or 0))
    elif m := _POST.fullmatch(rest):
        tail = (2, 0, int(m[1] or 0))
    else:
        raise ValueError(text)
    return (tuple(numbers), tail)


def older(theirs: object, ours: str) -> bool:
    """Whether version `theirs` predates `ours`; a missing or unreadable one counts as older."""
    try:
        return _order(theirs) < _order(ours)
    except ValueError:
        return True
