from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

MAX_FILE_BYTES = 10 * 1024 * 1024

CERTIFICATE_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
DATABASE_EXTENSIONS = {".sql", ".dump", ".db", ".sqlite", ".sqlite3"}
ML_ARTIFACT_EXTENSIONS = {".joblib", ".pkl", ".onnx", ".pt", ".bin"}
CACHE_EXTENSIONS = {".pyc", ".pyo"}
BUILD_DIRS = {"dist", "build"}
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"}
VIRTUAL_ENV_DIRS = {".venv", "venv", "env"}
NODE_DIRS = {"node_modules"}
BACKUP_DIRS = {"backups", "backup"}
LOG_DIRS = {"logs", "log"}
COVERAGE_PATHS = {".coverage", "coverage.xml", "htmlcov"}

KEY_HEADER_TERMS = (b"PRIVATE KEY", b"OPENSSH PRIVATE KEY")
KEY_HEADER_RE = re.compile(
    rb"-----BEGIN [A-Z0-9 ]*(?:" + b"|".join(KEY_HEADER_TERMS) + rb")[A-Z0-9 ]*-----"
)
CREDENTIAL_NAME_PATTERN = (
    r"[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|ACCESS_KEY|PRIVATE_KEY|CLIENT_SECRET)[A-Z0-9_]*"
)
CREDENTIAL_EQUALS_RE = re.compile(
    r"""(?imx)
    ^\s*
    (?:export\s+)?
    (?P<name>""" + CREDENTIAL_NAME_PATTERN + r""")
    (?:\s*:\s*[^=#]+)?
    \s*=\s*
    (?P<value>[^\s#]+)
    """
)
CREDENTIAL_YAML_RE = re.compile(
    r"""(?imx)
    ^\s*
    (?P<name>""" + CREDENTIAL_NAME_PATTERN + r""")
    \s*:\s*
    (?P<value>[^\s#]+)
    """
)
SAFE_NAME_SUFFIXES = ("_dir", "_path", "_file", "_header", "_headers")
PLACEHOLDER_MARKERS = (
    "<",
    "$",
    "os.getenv(",
    "getenv(",
    "settings.",
    "replace-",
    "placeholder",
    "example",
    "changeme",
    "change-me",
    "dummy",
    "test",
)
KNOWN_DEMO_VALUES = {"iot", "replace-with-a-long-local-demo-key"}


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str


def run_git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
    )


def staged_paths() -> list[str]:
    result = run_git(["diff", "--cached", "--name-only", "-z"])
    return [
        path.decode("utf-8", errors="surrogateescape")
        for path in result.stdout.split(b"\0")
        if path
    ]


def staged_size(path: str) -> int | None:
    blob = f":{path}"
    exists = subprocess.run(
        ["git", "cat-file", "-e", blob],
        check=False,
        capture_output=True,
    )
    if exists.returncode != 0:
        return None
    result = run_git(["cat-file", "-s", blob])
    return int(result.stdout.decode("ascii").strip())


def staged_content(path: str) -> bytes:
    return run_git(["show", f":{path}"]).stdout


def path_parts(path: str) -> list[str]:
    return [part.lower() for part in PurePosixPath(path).parts]


def path_findings(path: str) -> list[Finding]:
    normalized = path.replace("\\", "/")
    parts = path_parts(normalized)
    name = parts[-1] if parts else normalized.lower()
    suffix = PurePosixPath(name).suffix.lower()
    findings: list[Finding] = []

    if name != ".env.example" and (name == ".env" or name.startswith(".env.")):
        findings.append(Finding(path, "ENV_FILE"))
    if suffix in CERTIFICATE_EXTENSIONS or name.endswith(".keystore"):
        findings.append(Finding(path, "PRIVATE_KEY_OR_CERTIFICATE"))
    if suffix in ML_ARTIFACT_EXTENSIONS:
        findings.append(Finding(path, "GENERATED_ML_ARTIFACT"))
    if suffix in DATABASE_EXTENSIONS:
        findings.append(Finding(path, "DATABASE_DUMP"))
    if suffix in CACHE_EXTENSIONS or any(part in CACHE_DIRS for part in parts):
        findings.append(Finding(path, "CACHE_FILE"))
    if name == ".coverage" or name in COVERAGE_PATHS or any(part in COVERAGE_PATHS for part in parts):
        findings.append(Finding(path, "COVERAGE_OUTPUT"))
    if suffix == ".log" or any(part in LOG_DIRS for part in parts):
        findings.append(Finding(path, "LOG_FILE"))
    if any(part in BACKUP_DIRS for part in parts):
        findings.append(Finding(path, "BACKUP_FILE"))
    if any(part in NODE_DIRS for part in parts):
        findings.append(Finding(path, "NODE_MODULES"))
    if any(part in VIRTUAL_ENV_DIRS for part in parts):
        findings.append(Finding(path, "VIRTUAL_ENV"))
    if any(part in BUILD_DIRS for part in parts):
        findings.append(Finding(path, "BUILD_ARTIFACT"))
    return findings


def is_probably_text(content: bytes) -> bool:
    if b"\0" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def looks_like_placeholder(name: str, raw_value: str) -> bool:
    if name.lower().endswith(SAFE_NAME_SUFFIXES):
        return True
    value = raw_value.strip().strip("'\"").lower()
    if not value or value in KNOWN_DEMO_VALUES:
        return True
    if any(marker in value for marker in PLACEHOLDER_MARKERS):
        return True
    if "(" in value and value.endswith(")"):
        return True
    raw_stripped = raw_value.strip().strip("'\"")
    return bool(re.fullmatch(r"[A-Z_][A-Z0-9_]*", raw_stripped) and "_" in raw_stripped)


def content_findings(path: str, content: bytes) -> list[Finding]:
    findings: list[Finding] = []
    if KEY_HEADER_RE.search(content):
        findings.append(Finding(path, "CONTENT_PRIVATE_KEY_HEADER"))
    if not is_probably_text(content):
        return findings
    text = content.decode("utf-8", errors="replace")
    patterns = [CREDENTIAL_EQUALS_RE]
    if PurePosixPath(path).suffix.lower() in {".yml", ".yaml"}:
        patterns.append(CREDENTIAL_YAML_RE)
    for pattern in patterns:
        for match in pattern.finditer(text):
            if looks_like_placeholder(match.group("name"), match.group("value")):
                continue
            findings.append(Finding(path, "CONTENT_CREDENTIAL_ASSIGNMENT"))
            return findings
    return findings


def inspect_staged_files(
    paths: Iterable[str],
    *,
    size_reader: Callable[[str], int | None],
    content_reader: Callable[[str], bytes],
) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        findings.extend(path_findings(path))
        size = size_reader(path)
        if size is None:
            continue
        if size > MAX_FILE_BYTES:
            findings.append(Finding(path, "FILE_TOO_LARGE"))
            continue
        findings.extend(content_findings(path, content_reader(path)))
    return findings


def format_findings(findings: Iterable[Finding]) -> str:
    return "\n".join(f"{finding.path}\t{finding.rule}" for finding in findings)


def main() -> int:
    findings = inspect_staged_files(
        staged_paths(),
        size_reader=staged_size,
        content_reader=staged_content,
    )
    if findings:
        print(format_findings(findings), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
