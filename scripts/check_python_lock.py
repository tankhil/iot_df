from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LockSpec:
    label: str
    output: Path
    args: tuple[str, ...]


LOCK_SPECS = (
    LockSpec(
        label="runtime",
        output=ROOT / "backend" / "requirements.lock",
        args=(
            "uv",
            "--quiet",
            "pip",
            "compile",
            "backend/pyproject.toml",
            "--python-version",
            "3.12",
            "--universal",
            "--generate-hashes",
            "--output-file",
        ),
    ),
    LockSpec(
        label="build",
        output=ROOT / "backend" / "build-requirements.lock",
        args=(
            "uv",
            "--quiet",
            "pip",
            "compile",
            "backend/build-requirements.in",
            "--python-version",
            "3.12",
            "--universal",
            "--generate-hashes",
            "--output-file",
        ),
    ),
    LockSpec(
        label="dev",
        output=ROOT / "backend" / "requirements-dev.lock",
        args=(
            "uv",
            "--quiet",
            "pip",
            "compile",
            "backend/pyproject.toml",
            "backend/build-requirements.in",
            "--extra",
            "dev",
            "--python-version",
            "3.12",
            "--universal",
            "--generate-hashes",
            "--output-file",
        ),
    ),
)


def compile_lock(spec: LockSpec, output: Path) -> None:
    command = [
        *spec.args,
        str(output),
        "--custom-compile-command",
        "make python-lock",
    ]
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/tmp/iot-df-uv-cache")
    env.setdefault("UV_PYTHON_DOWNLOADS", "never")
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def lock_is_current(spec: LockSpec, generated: Path) -> bool:
    if not spec.output.exists():
        print(f"Missing Python {spec.label} lock: {display_path(spec.output)}", file=sys.stderr)
        return False
    return spec.output.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8")


def main() -> int:
    stale: list[str] = []
    with tempfile.TemporaryDirectory(prefix="python-lock-check-") as tmpdir:
        tmp = Path(tmpdir)
        for spec in LOCK_SPECS:
            generated = tmp / spec.output.name
            compile_lock(spec, generated)
            if not lock_is_current(spec, generated):
                stale.append(display_path(spec.output))
    if stale:
        print("Stale Python lock file(s):", file=sys.stderr)
        for path in stale:
            print(f"  {path}", file=sys.stderr)
        print("Run `make python-lock` and review the generated diff.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
