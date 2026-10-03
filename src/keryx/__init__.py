import re


def version() -> str:
    """The installed keryx version; looked up on demand, since hooks import this package."""
    from importlib.metadata import version as installed

    return installed("keryx")


def _order(text: object) -> tuple:
    """A sort key for a version such as 0.5.1, 0.5.1rc1 or 0.5.1.post1; ValueError if unreadable."""
    found = re.fullmatch(r"(\d+(?:\.\d+)*)(.*)", str(text).strip())
    if found is None:
        raise ValueError(text)
    numbers = [int(n) for n in found[1].split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()  # 0.5 is 0.5.0
    rest = found[2]
    stage = 1 if not rest else 2 if rest.lstrip(".-_").startswith("post") else 0
    return (tuple(numbers), stage, rest)


def older(theirs: object, ours: str) -> bool:
    """Whether version `theirs` predates `ours`; a missing or unreadable one counts as older."""
    try:
        return _order(theirs) < _order(ours)
    except ValueError:
        return True
