"""Build Debian APT repository metadata and fail closed for stable GPG publication."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from judge import __version__

PACKAGE_NAME = "algorithm-local-judge"
BOOTSTRAP_PACKAGE_NAME = "algorithm-local-judge-archive-keyring"
KEYRING_PATH = f"/usr/share/keyrings/{BOOTSTRAP_PACKAGE_NAME}.gpg"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ValueError(f"{name} is required to build the APT repository")
    return path


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"command failed ({command[0]}): {detail}")
    return result


def validate_repository_url(repository_url: str) -> str:
    normalized = repository_url.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("stable APT repository URL must be an absolute HTTPS URL")
    return normalized


def packages_text(deb: Path, version: str) -> str:
    return f"""Package: {PACKAGE_NAME}
Version: {version}
Architecture: amd64
Filename: pool/main/a/{PACKAGE_NAME}/{deb.name}
Size: {deb.stat().st_size}
SHA256: {sha256(deb)}
Description: Local web judge and problem authoring studio

"""


def release_text(repository: Path, source_date_epoch: int) -> str:
    files = [
        repository / "dists" / "stable" / "main" / "binary-amd64" / "Packages",
        repository / "dists" / "stable" / "main" / "binary-amd64" / "Packages.gz",
    ]
    date = datetime.fromtimestamp(source_date_epoch, tz=UTC).strftime("%a, %d %b %Y %H:%M:%S UTC")
    lines = [
        "Origin: Algorithm Local Judge",
        "Label: Algorithm Local Judge",
        "Suite: stable",
        "Codename: stable",
        "Architectures: amd64",
        "Components: main",
        f"Date: {date}",
        "SHA256:",
    ]
    for path in files:
        relative = path.relative_to(repository / "dists" / "stable").as_posix()
        lines.append(f" {sha256(path)} {path.stat().st_size:16d} {relative}")
    return "\n".join(lines) + "\n"


def stage_repository(deb: Path, repository: Path, version: str, source_date_epoch: int) -> Path:
    pool = repository / "pool" / "main" / "a" / PACKAGE_NAME
    pool.mkdir(parents=True, exist_ok=True)
    shutil.copy2(deb, pool / deb.name)
    binary = repository / "dists" / "stable" / "main" / "binary-amd64"
    binary.mkdir(parents=True, exist_ok=True)
    packages = binary / "Packages"
    packages.write_text(packages_text(deb, version), encoding="utf-8")
    with packages.open("rb") as source, (binary / "Packages.gz").open("wb") as target:
        with gzip.GzipFile(fileobj=target, mode="wb", mtime=source_date_epoch) as compressed:
            shutil.copyfileobj(source, compressed)
    release = repository / "dists" / "stable" / "Release"
    release.write_text(release_text(repository, source_date_epoch), encoding="utf-8")
    return release


def gpg_fingerprint(gpg: str, key_id: str) -> str:
    result = run_checked([gpg, "--batch", "--with-colons", "--fingerprint", key_id])
    return fingerprint_from_output(result.stdout, "APT signing key")


def fingerprint_from_output(output: str, label: str) -> str:
    for line in output.splitlines():
        fields = line.split(":")
        if (
            fields[0] == "fpr"
            and len(fields) > 9
            and re.fullmatch(r"[0-9A-Fa-f]{40,64}", fields[9])
        ):
            return fields[9].upper()
    raise ValueError(f"{label} fingerprint could not be determined")


def public_key_fingerprint(public_key: Path) -> str:
    gpg = require_tool("gpg")
    result = run_checked(
        [gpg, "--batch", "--with-colons", "--show-keys", "--fingerprint", str(public_key)]
    )
    return fingerprint_from_output(result.stdout, "APT public key")


def sign_release(release: Path, key_id: str) -> dict[str, str]:
    gpg = require_tool("gpg")
    fingerprint = gpg_fingerprint(gpg, key_id)
    detached = release.with_name("Release.gpg")
    inline = release.with_name("InRelease")
    common = [gpg, "--batch", "--yes", "--local-user", key_id]
    run_checked([*common, "--armor", "--detach-sign", "--output", str(detached), str(release)])
    run_checked([*common, "--armor", "--clearsign", "--output", str(inline), str(release)])
    run_checked([gpg, "--batch", "--verify", str(detached), str(release)])
    run_checked([gpg, "--batch", "--verify", str(inline)])
    return {"provider": "openpgp", "keyFingerprint": fingerprint, "releaseSha256": sha256(release)}


def bootstrap_control(version: str) -> str:
    return f"""Package: {BOOTSTRAP_PACKAGE_NAME}
Version: {version}
Section: admin
Priority: optional
Architecture: all
Maintainer: Algorithm Local Judge maintainers
Description: APT signing key and repository configuration for Algorithm Local Judge
"""


def build_bootstrap_package(
    repository_url: str,
    public_key: Path,
    output_dir: Path,
    version: str,
) -> Path:
    dpkg_deb = require_tool("dpkg-deb")
    if not public_key.is_file() or public_key.stat().st_size == 0:
        raise ValueError("APT public key file is missing or empty")
    repository_url = validate_repository_url(repository_url)
    output = output_dir / f"{BOOTSTRAP_PACKAGE_NAME}_{version}_all.deb"
    with tempfile.TemporaryDirectory(prefix="alj-apt-bootstrap-") as tmp:
        stage = Path(tmp) / "root"
        control = stage / "DEBIAN" / "control"
        control.parent.mkdir(parents=True, exist_ok=True)
        control.write_text(bootstrap_control(version), encoding="utf-8")
        keyring = stage / KEYRING_PATH.removeprefix("/")
        keyring.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(public_key, keyring)
        sources = stage / "etc" / "apt" / "sources.list.d" / f"{PACKAGE_NAME}.sources"
        sources.parent.mkdir(parents=True, exist_ok=True)
        sources.write_text(
            "\n".join(
                [
                    "Types: deb",
                    f"URIs: {repository_url}",
                    "Suites: stable",
                    "Components: main",
                    f"Signed-By: {KEYRING_PATH}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        run_checked([dpkg_deb, "--root-owner-group", "--build", str(stage), str(output)])
    if not output.is_file():
        raise ValueError("dpkg-deb did not produce the APT bootstrap package")
    return output


def archive_repository(repository: Path, output: Path) -> None:
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(repository.rglob("*")):
            archive.add(path, arcname=path.relative_to(repository), recursive=False)


def build_apt_repository(
    deb: Path,
    output_dir: Path,
    version: str,
    *,
    stable: bool,
    gpg_key_id: str = "",
    repository_url: str = "",
    public_key: Path | None = None,
    source_date_epoch: int = 0,
) -> tuple[Path, Path | None, Path]:
    if not deb.is_file():
        raise ValueError(f"Debian package does not exist: {deb}")
    if stable and not gpg_key_id.strip():
        raise ValueError("ALJ_APT_GPG_KEY_ID is required for a stable APT repository")
    if stable and (not repository_url or public_key is None):
        raise ValueError("stable APT repository URL and public key are required")
    if bool(repository_url) != (public_key is not None):
        raise ValueError("APT repository URL and public key must be provided together")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{PACKAGE_NAME}-{version}-apt-repository.tar.gz"
    evidence_path = output_dir / f"{archive.name}.native-signing.json"
    with tempfile.TemporaryDirectory(prefix="alj-apt-repository-") as tmp:
        repository = Path(tmp) / "repository"
        release = stage_repository(deb.resolve(), repository, version, source_date_epoch)
        attestation = sign_release(release, gpg_key_id.strip()) if stable else None
        if (
            stable
            and public_key is not None
            and public_key_fingerprint(public_key) != attestation["keyFingerprint"]
        ):
            raise ValueError("APT public key does not match the Release signing key")
        archive_repository(repository, archive)
    bootstrap = None
    if repository_url and public_key is not None:
        bootstrap = build_bootstrap_package(
            repository_url, public_key.resolve(), output_dir, version
        )
    evidence = {
        "schemaVersion": 1,
        "target": "apt",
        "type": "apt-gpg",
        "status": "verified" if stable else "unconfigured",
        "artifact": {"name": archive.name, "sha256": sha256(archive)},
        "attestation": attestation,
    }
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return archive, bootstrap, evidence_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/installers"))
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--channel", choices=["candidate", "stable"], default="candidate")
    parser.add_argument("--gpg-key-id", default=os.environ.get("ALJ_APT_GPG_KEY_ID", ""))
    parser.add_argument("--repository-url", default=os.environ.get("APT_REPOSITORY_URL", ""))
    parser.add_argument("--public-key", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "0")),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        archive, bootstrap, evidence = build_apt_repository(
            args.deb,
            args.output_dir,
            args.version,
            stable=args.channel == "stable",
            gpg_key_id=args.gpg_key_id,
            repository_url=args.repository_url,
            public_key=args.public_key,
            source_date_epoch=args.source_date_epoch,
        )
    except (OSError, ValueError, tarfile.TarError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"Built APT repository archive: {archive}")
    if bootstrap is not None:
        print(f"Built APT bootstrap package: {bootstrap}")
    print(f"Built native signing evidence: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
