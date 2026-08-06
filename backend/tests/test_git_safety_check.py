import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "git_safety_check.py"
SPEC = importlib.util.spec_from_file_location("git_safety_check", SCRIPT_PATH)
assert SPEC is not None
git_safety_check = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["git_safety_check"] = git_safety_check
SPEC.loader.exec_module(git_safety_check)


def inspect(files: dict[str, bytes], sizes: dict[str, int] | None = None):
    sizes = sizes or {}

    def size_reader(path: str) -> int:
        return sizes.get(path, len(files[path]))

    def content_reader(path: str) -> bytes:
        return files[path]

    return git_safety_check.inspect_staged_files(
        files,
        size_reader=size_reader,
        content_reader=content_reader,
    )


def rules(findings) -> set[str]:
    return {finding.rule for finding in findings}


def test_safe_source_file_is_allowed() -> None:
    findings = inspect({"backend/app/example.py": b"def example() -> str:\n    return 'ok'\n"})

    assert findings == []


def test_env_file_is_rejected() -> None:
    findings = inspect({".env": b"ADMIN_API_KEY=not-for-output\n"})

    assert "ENV_FILE" in rules(findings)


def test_env_example_placeholder_is_allowed() -> None:
    findings = inspect({".env.example": b"ADMIN_API_KEY=replace-with-a-long-local-demo-key\n"})

    assert findings == []


def test_generated_model_is_rejected() -> None:
    findings = inspect({"models/isolation_forest_global.joblib": b"model-bytes"})

    assert "GENERATED_ML_ARTIFACT" in rules(findings)


def test_private_key_header_is_rejected_without_printing_value() -> None:
    header = b"-----BEGIN " + b"PRIVATE " + b"KEY-----"
    findings = inspect({"docs/example.txt": header + b"\nsecret-value\n"})
    output = git_safety_check.format_findings(findings)

    assert "CONTENT_PRIVATE_KEY_HEADER" in rules(findings)
    assert "secret-value" not in output
    assert "docs/example.txt" in output


def test_oversized_file_is_rejected() -> None:
    findings = inspect(
        {"docs/large.txt": b""},
        sizes={"docs/large.txt": git_safety_check.MAX_FILE_BYTES + 1},
    )

    assert "FILE_TOO_LARGE" in rules(findings)


def test_filename_with_spaces_is_handled() -> None:
    findings = inspect({"docs/file with spaces.md": b"# Safe\n"})

    assert findings == []


def run_checker_in_repo(tmp_path: Path, files: dict[str, bytes]) -> subprocess.CompletedProcess[str]:
    script_target = tmp_path / "scripts" / "git_safety_check.py"
    script_target.parent.mkdir(parents=True)
    script_target.write_bytes(SCRIPT_PATH.read_bytes())
    for relative_path, content in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init"], cwd=tmp_path, check=True, capture_output=True)  # noqa: S603
    subprocess.run([git, "add", "."], cwd=tmp_path, check=True, capture_output=True)  # noqa: S603
    return subprocess.run(
        [sys.executable, "scripts/git_safety_check.py"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )


def test_checker_and_tests_can_be_staged_safely(tmp_path: Path) -> None:
    result = run_checker_in_repo(
        tmp_path,
        {"backend/tests/test_git_safety_check.py": Path(__file__).read_bytes()},
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_other_staged_file_with_private_key_header_is_rejected(tmp_path: Path) -> None:
    header = b"-----BEGIN " + b"PRIVATE " + b"KEY-----"
    result = run_checker_in_repo(
        tmp_path,
        {"docs/leaked.txt": header + b"\nnot-printed\n"},
    )

    assert result.returncode != 0
    assert "docs/leaked.txt\tCONTENT_PRIVATE_KEY_HEADER" in result.stderr
    assert "not-printed" not in result.stderr


def test_other_staged_file_with_credential_assignment_is_rejected_without_value(tmp_path: Path) -> None:
    value = "not-printed-value"
    content = ("API_" + "TOKEN=" + value + "\n").encode()
    result = run_checker_in_repo(
        tmp_path,
        {"docs/credentials.txt": content},
    )

    assert result.returncode != 0
    assert "docs/credentials.txt\tCONTENT_CREDENTIAL_ASSIGNMENT" in result.stderr
    assert value not in result.stderr
