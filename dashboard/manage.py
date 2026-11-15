#!/usr/bin/env python
"""Django management entry point for the ChopCast dashboard."""

from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ImportError(
            "Django is not installed. Create dashboard/.venv with Python 3.11-3.13 "
            "and run: pip install -e '.[dev]'"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
