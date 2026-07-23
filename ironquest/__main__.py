"""Allow running the project with ``python -m ironquest``."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
