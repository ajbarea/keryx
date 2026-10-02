def version() -> str:
    """The installed keryx version; looked up on demand, since hooks import this package."""
    from importlib.metadata import version as installed

    return installed("keryx")


def older(theirs: object, ours: str) -> bool:
    """Whether version `theirs` predates `ours`; a missing or unreadable one counts as older."""
    try:
        return tuple(map(int, str(theirs).split("."))) < tuple(map(int, ours.split(".")))
    except ValueError:
        return True
