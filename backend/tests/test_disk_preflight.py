import shutil
from pathlib import Path

from scripts import disk_preflight


def usage_with_free(free_gib: int):
    total = 20 * disk_preflight.GIB
    free = free_gib * disk_preflight.GIB
    used = total - free
    return shutil._ntuple_diskusage(total=total, used=used, free=free)


def test_disk_preflight_passes_at_eight_gib() -> None:
    result = disk_preflight.check_disk_space(
        Path("/project"),
        usage_reader=lambda path: usage_with_free(8),
        docker_root_reader=lambda: None,
    )

    assert result.status == "PASS"
    assert result.reports[0].status == "PASS"


def test_disk_preflight_warns_between_five_and_eight_gib() -> None:
    result = disk_preflight.check_disk_space(
        Path("/project"),
        usage_reader=lambda path: usage_with_free(6),
        docker_root_reader=lambda: None,
    )

    assert result.status == "WARN"
    assert result.reports[0].status == "WARN"


def test_disk_preflight_fails_below_five_gib() -> None:
    result = disk_preflight.check_disk_space(
        Path("/project"),
        usage_reader=lambda path: usage_with_free(4),
        docker_root_reader=lambda: None,
    )

    assert result.status == "FAIL"
    assert result.reports[0].status == "FAIL"


def test_disk_preflight_checks_docker_root_when_available() -> None:
    usages = {
        Path("/project"): usage_with_free(9),
        Path("/var/lib/docker"): usage_with_free(6),
    }
    result = disk_preflight.check_disk_space(
        Path("/project"),
        usage_reader=lambda path: usages[path],
        docker_root_reader=lambda: Path("/var/lib/docker"),
    )

    assert [report.name for report in result.reports] == ["project", "docker-data"]
    assert result.status == "WARN"
    assert result.reports[1].status == "WARN"
