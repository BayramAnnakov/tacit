"""Entry point for `tacit` CLI command when installed via pip/uvx.

Bootstraps sys.path and delegates to the backend __main__ module.

Usage:
    tacit openclaw/openclaw --demo          # Demo mode (no API keys needed)
    tacit owner/repo                        # Full extraction (needs .env)
    tacit owner/repo --skip-extract --summary  # Reuse existing DB
"""

import importlib.util
import os
import sys
from pathlib import Path


def main() -> None:
    # Remove CLAUDECODE env var to allow nested Claude SDK calls
    os.environ.pop("CLAUDECODE", None)

    # Add backend directory to path so its local imports work
    backend_dir = Path(__file__).parent / "tacit" / "backend"
    sys.path.insert(0, str(backend_dir))

    # Change working directory to backend so .env and DB paths resolve
    os.chdir(str(backend_dir))

    # Load the backend __main__ module via importlib (avoids package import issues)
    spec = importlib.util.spec_from_file_location(
        "tacit_backend_main", str(backend_dir / "__main__.py")
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    import asyncio
    sys.exit(asyncio.run(mod.main()))


if __name__ == "__main__":
    main()
