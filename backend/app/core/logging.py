import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if not any(getattr(h, "_brandpr", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler._brandpr = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    root.setLevel(level.upper())
