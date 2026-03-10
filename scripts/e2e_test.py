#!/usr/bin/env python3
"""E2E test suite entry point. See scripts/e2e/ for implementation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    try:
        from e2e.main import main

        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted (Ctrl+C). Cleaning up...")
        sys.exit(130)
