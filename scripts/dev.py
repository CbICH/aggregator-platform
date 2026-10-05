"""Run Compose safely from paths containing Cyrillic (Docker BuildKit header limitation)."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns(
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".env",
    ".env.*",
    "*.db",
    "*.db-shm",
    "*.db-wal",
    "test-results",
    "*.tsbuildinfo",
)


def compose(directory: Path, args: list[str]) -> int:
    command = ["docker", "compose", "--project-name", "fsp-signal"]
    if (ROOT / ".env").exists():
        command.extend(["--env-file", str(ROOT / ".env")])
    return subprocess.call(command + args, cwd=directory)


def main() -> int:
    args = sys.argv[1:] or ["up", "-d", "--build", "--wait"]
    building = "build" in args or "--build" in args
    if str(ROOT).isascii() or not building:
        return compose(ROOT, args)
    with tempfile.TemporaryDirectory(prefix="fsp-signal-build-") as name:
        staging = Path(name)
        if not str(staging).isascii():
            raise SystemExit("Set TMPDIR to an ASCII path for Docker BuildKit")
        for folder in ("apps", "infra"):
            shutil.copytree(ROOT / folder, staging / folder, ignore=IGNORE)
        for file in ("docker-compose.yml", ".dockerignore"):
            shutil.copy2(ROOT / file, staging / file)
        print(
            "Building from a temporary ASCII path; source files and database volume stay in place.",
            flush=True,
        )
        return compose(staging, args)


if __name__ == "__main__":
    raise SystemExit(main())
