from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3
FAIL_FREE_BYTES = 5 * GIB
WARN_FREE_BYTES = 8 * GIB
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DiskReport:
    name: str
    path: Path
    total: int
    used: int
    free: int
    used_percent: float
    status: str


@dataclass(frozen=True)
class DiskCheckResult:
    reports: list[DiskReport]
    skipped: list[str]

    @property
    def status(self) -> str:
        statuses = {report.status for report in self.reports}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"


def classify_free_space(free: int) -> str:
    if free < FAIL_FREE_BYTES:
        return "FAIL"
    if free < WARN_FREE_BYTES:
        return "WARN"
    return "PASS"


def gibibytes(value: int) -> float:
    return value / GIB


def inspect_path(
    name: str,
    path: Path,
    *,
    usage_reader: Callable[[Path], shutil._ntuple_diskusage],
) -> DiskReport:
    usage = usage_reader(path)
    used_percent = (usage.used / usage.total * 100.0) if usage.total else 0.0
    return DiskReport(
        name=name,
        path=path,
        total=usage.total,
        used=usage.used,
        free=usage.free,
        used_percent=used_percent,
        status=classify_free_space(usage.free),
    )


def detect_docker_root() -> Path | None:
    docker = shutil.which("docker")
    if docker is None:
        return None
    result = subprocess.run(
        [docker, "info", "--format", "{{.DockerRootDir}}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return Path(value) if value else None


def check_disk_space(
    project_path: Path = ROOT,
    *,
    usage_reader: Callable[[Path], shutil._ntuple_diskusage] = shutil.disk_usage,
    docker_root_reader: Callable[[], Path | None] = detect_docker_root,
) -> DiskCheckResult:
    reports: list[DiskReport] = []
    skipped: list[str] = []

    reports.append(inspect_path("project", project_path, usage_reader=usage_reader))

    docker_root = docker_root_reader()
    if docker_root is None:
        skipped.append("docker-data: Docker root unavailable")
    else:
        try:
            reports.append(inspect_path("docker-data", docker_root, usage_reader=usage_reader))
        except OSError as exc:
            skipped.append(f"docker-data: {docker_root} unavailable ({exc.__class__.__name__})")

    return DiskCheckResult(reports=reports, skipped=skipped)


def format_report(result: DiskCheckResult) -> str:
    lines = ["DISK_PREFLIGHT_RESULT=" + result.status]
    lines.append("target\tpath\ttotal_gib\tused_gib\tfree_gib\tused_percent\tstatus")
    for report in result.reports:
        lines.append(
            "\t".join(
                [
                    report.name,
                    str(report.path),
                    f"{gibibytes(report.total):.1f}",
                    f"{gibibytes(report.used):.1f}",
                    f"{gibibytes(report.free):.1f}",
                    f"{report.used_percent:.1f}%",
                    report.status,
                ]
            )
        )
    for message in result.skipped:
        lines.append(f"SKIPPED\t{message}")
    if result.status in {"WARN", "FAIL"}:
        lines.extend(
            [
                "",
                "Manual cleanup candidates were not executed:",
                "- docker system df: shows Docker image, container, volume, and build-cache usage.",
                "- docker builder prune: deletes unused Docker build cache only.",
                "- docker image prune: deletes dangling untagged Docker images only.",
                "- docker system prune: deletes stopped containers, unused networks, dangling images, and build cache; it does not delete volumes unless --volumes is added.",
                "- docker volume prune: deletes all unused local Docker volumes, including database volumes from other projects if they are unused.",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    result = check_disk_space()
    print(format_report(result))
    return 1 if result.status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
