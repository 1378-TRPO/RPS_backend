"""Cross-platform development commands; use the project's virtual environment."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = {
    "run": [("uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000")],
    "test": [("pytest",)],
    "lint": [("ruff", "check", "."), ("ruff", "format", "--check", ".")],
    "format": [("ruff", "check", "--fix", "."), ("ruff", "format", ".")],
    "check": [("ruff", "check", "."), ("ruff", "format", "--check", "."), ("pytest",)],
    "migrate": [("alembic", "upgrade", "head")],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    for command in COMMANDS[args.command]:
        result = subprocess.run([sys.executable, "-m", *command], cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
