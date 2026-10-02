def version() -> str:
    """The installed keryx version; looked up on demand, since hooks import this package."""
    from importlib.metadata import version as installed

    return installed("keryx")
