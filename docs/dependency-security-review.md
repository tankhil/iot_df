# Dependency Security Reproducibility Review

Review date: 2026-08-10

## Python Locks

Python dependency changes are reproducible through generated, committed, hash-pinned pip lock files:

- `backend/requirements.lock`: runtime Python dependencies only.
- `backend/build-requirements.lock`: build backend needed to install the local backend package with `--no-build-isolation`.
- `backend/requirements-dev.lock`: development, test, lint, type-check, audit, lock-check, runtime, and build dependencies.

Regenerate them with:

```bash
make python-lock
```

Check freshness with:

```bash
make dependency-lock-check
```

Docker installs `backend/requirements.lock` with `--require-hashes`, installs `backend/build-requirements.lock` with `--require-hashes`, installs the local backend package with `--no-build-isolation --no-deps`, then removes `setuptools` from the final backend image. CI installs `backend/requirements-dev.lock` with `--require-hashes`, then installs the local backend editable package with `--no-build-isolation --no-deps -e backend`.

## GitHub Actions Pins

Every third-party action in `.github/workflows/ci.yml` is pinned to a full 40-character commit SHA with a release comment:

| Action | Release comment | Commit SHA |
| --- | --- | --- |
| `actions/checkout` | `v4.4.0` | `11d5960a326750d5838078e36cf38b85af677262` |
| `actions/setup-python` | `v5.6.0` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/setup-node` | `v4.4.0` | `49933ea5288caeca8642d1e84afbd3f7d6820020` |
| `aquasecurity/trivy-action` | `v0.36.0` | `ed142fd0673e97e23eac54620cfb913e5ce36c25` |

Dependabot remains enabled for GitHub Actions updates in `.github/dependabot.yml`.

## Docker Base Images

The unconditional Debian package upgrade was removed from the backend Dockerfile. Runtime images now depend on digest-pinned maintained base images:

| Image use | Pinned image |
| --- | --- |
| Backend runtime | `python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2` |
| Dashboard build | `node:20.19.5-bookworm-slim@sha256:9e70124bd00f47dd023e349cd587132ae61892acc0e47ed641416c3e18f401c3` |
| Dashboard runtime | `busybox:1.37.0-uclibc@sha256:8d7b1636e974e0adfd8d945955fca609304f0a56c18799dfd032d6e661382d84` |
| Compose PostgreSQL | `postgres:16.10-bookworm@sha256:38471f330eb885e04de130b768d6db4e10469e2311879c7e5c699f6d2d8a1c74` |
| Compose MQTT broker | `eclipse-mosquitto:2.0.22@sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c` |

No project Dockerfile currently installs OS packages. If that becomes necessary, install only required packages, use `--no-install-recommends`, and remove apt indexes in the same layer. The tradeoff is that digest-pinned images do not pick up patched Debian packages implicitly on every build; patches arrive through reviewed Dependabot Docker digest/tag update PRs instead of unbounded build-time upgrades.

## Scanner Policy

CI reports all runtime OS vulnerabilities with `ignore-unfixed: false` so unfixed findings stay visible. CI separately fails on fixed high/critical runtime OS vulnerabilities with `ignore-unfixed: true`, which is the reliable Trivy mode for distinguishing findings that have an available patched package.

Trivy 0.67.2 scan evidence from 2026-08-10:

- Backend runtime image: 196 total unfixed Debian OS findings, including the 24 high/critical findings listed below; 0 fixed OS findings.
- Dashboard runtime image: 0 OS findings.

The 24 high/critical backend OS findings are not ignored or suppressed:

| Package | Installed version | Vulnerability | Severity | Fix availability |
| --- | --- | --- | --- | --- |
| `bsdutils` | `1:2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `gzip` | `1.12-1` | `CVE-2026-41992` | HIGH | No fixed version reported by Trivy |
| `libacl1` | `2.3.1-3` | `CVE-2026-54369` | HIGH | No fixed version reported by Trivy |
| `libblkid1` | `2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `libmount1` | `2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `libncursesw6` | `6.4-4` | `CVE-2025-69720` | HIGH | No fixed version reported by Trivy |
| `libsmartcols1` | `2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `libsqlite3-0` | `3.40.1-2+deb12u2` | `CVE-2025-7458` | CRITICAL | No fixed version reported by Trivy |
| `libtinfo6` | `6.4-4` | `CVE-2025-69720` | HIGH | No fixed version reported by Trivy |
| `libuuid1` | `2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `mount` | `2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `ncurses-base` | `6.4-4` | `CVE-2025-69720` | HIGH | No fixed version reported by Trivy |
| `ncurses-bin` | `6.4-4` | `CVE-2025-69720` | HIGH | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-13221` | CRITICAL | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-42496` | CRITICAL | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-42497` | HIGH | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-48962` | HIGH | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-57432` | HIGH | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-57433` | CRITICAL | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-8376` | CRITICAL | No fixed version reported by Trivy |
| `perl-base` | `5.36.0-7+deb12u3` | `CVE-2026-9538` | HIGH | No fixed version reported by Trivy |
| `util-linux` | `2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `util-linux-extra` | `2.38.1-5+deb12u3` | `CVE-2026-53615` | HIGH | No fixed version reported by Trivy |
| `zlib1g` | `1:1.2.13.dfsg-1` | `CVE-2023-45853` | CRITICAL | No fixed version reported by Trivy |
