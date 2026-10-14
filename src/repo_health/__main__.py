"""Entry point for ``python -m repo_health``."""

from __future__ import annotations

from repo_health.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
