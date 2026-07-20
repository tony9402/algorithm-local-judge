"""Generate WiX v4 source and optionally build the Windows x64 MSI."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from alj_core.errors import JudgeError
from alj_core.pack_archive import safe_extract_tar
from judge import __version__
from judge.core.paths import current_platform_id

PACKAGE_NAME = "algorithm-local-judge"
SUPPORTED_PLATFORM = "windows-amd64"
WIX_NAMESPACE = "http://wixtoolset.org/schemas/v4/wxs"
UPGRADE_CODE = "84D9A2E1-A2E7-4B2C-9D6F-7B6D48644191"
COMPONENT_NAMESPACE = uuid.UUID("2649127d-1d8a-4bea-8a7e-0f3f56c19f48")


def validate_windows_platform(platform_id: str, current: str | None = None) -> None:
    if platform_id != SUPPORTED_PLATFORM:
        raise ValueError(f"unsupported Windows installer platform: {platform_id}")
    host = current or current_platform_id()
    if host != SUPPORTED_PLATFORM:
        raise ValueError(f"MSI builds require a windows-amd64 host, current platform is {host}")


def msi_version(version: str) -> str:
    parts = version.split(".")
    if not 1 <= len(parts) <= 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"MSI version must contain one to three numeric fields: {version}")
    values = [int(part) for part in parts]
    if any(value < 0 or value > 65535 for value in values):
        raise ValueError(f"MSI version field is out of range: {version}")
    return ".".join(str(value) for value in values + [0] * (3 - len(values)))


def stage_windows_standalone(archive_path: Path, stage: Path) -> Path:
    if not archive_path.is_file():
        raise ValueError(f"Windows standalone archive not found: {archive_path}")
    safe_extract_tar(archive_path, stage)
    app_root = stage / PACKAGE_NAME
    for launcher in ("judge.exe", "problem-studio.exe"):
        if not (app_root / "bin" / launcher).is_file():
            raise ValueError(f"Windows standalone has no launcher: bin/{launcher}")
    return app_root


def wix_id(prefix: str, value: str) -> str:
    compact = uuid.uuid5(COMPONENT_NAMESPACE, value).hex
    return f"{prefix}_{compact}"


def add_directory_contents(
    directory_element: ET.Element,
    directory: Path,
    relative: Path,
    component_ids: list[str],
) -> None:
    for path in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        child_relative = relative / path.name
        if path.is_dir():
            child = ET.SubElement(
                directory_element,
                "Directory",
                {"Id": wix_id("DIR", child_relative.as_posix()), "Name": path.name},
            )
            add_directory_contents(child, path, child_relative, component_ids)
            continue
        component_id = wix_id("CMP", child_relative.as_posix())
        component = ET.SubElement(
            directory_element,
            "Component",
            {
                "Id": component_id,
                "Guid": str(uuid.uuid5(COMPONENT_NAMESPACE, child_relative.as_posix())).upper(),
                "Bitness": "always64",
            },
        )
        ET.SubElement(
            component,
            "File",
            {
                "Id": wix_id("FIL", child_relative.as_posix()),
                "Source": str(path.resolve()),
                "KeyPath": "yes",
            },
        )
        component_ids.append(component_id)


def wix_source(app_root: Path, version: str) -> str:
    for launcher in ("judge.exe", "problem-studio.exe"):
        if not (app_root / "bin" / launcher).is_file():
            raise ValueError(f"Windows standalone has no launcher: bin/{launcher}")
    ET.register_namespace("", WIX_NAMESPACE)
    wix = ET.Element(f"{{{WIX_NAMESPACE}}}Wix")
    package = ET.SubElement(
        wix,
        "Package",
        {
            "Name": "Algorithm Local Judge",
            "Manufacturer": "Algorithm Local Judge maintainers",
            "Version": msi_version(version),
            "UpgradeCode": UPGRADE_CODE,
            "Scope": "perMachine",
            "Platform": "x64",
        },
    )
    ET.SubElement(
        package,
        "MajorUpgrade",
        {"DowngradeErrorMessage": "A newer Algorithm Local Judge version is installed."},
    )
    ET.SubElement(package, "MediaTemplate", {"EmbedCab": "yes"})
    ET.SubElement(
        package,
        "Launch",
        {
            "Condition": "VersionNT64 >= 1000",
            "Message": "Algorithm Local Judge requires 64-bit Windows 10 or later.",
        },
    )
    program_files = ET.SubElement(package, "StandardDirectory", {"Id": "ProgramFiles64Folder"})
    install = ET.SubElement(
        program_files,
        "Directory",
        {"Id": "INSTALLFOLDER", "Name": "Algorithm Local Judge"},
    )
    component_ids: list[str] = []
    add_directory_contents(install, app_root, Path(), component_ids)
    bin_directory_id = wix_id("DIR", "bin")
    bin_directory = next(
        element for element in install.iter("Directory") if element.get("Id") == bin_directory_id
    )
    path_component_id = "PathEnvironmentComponent"
    path_component = ET.SubElement(
        bin_directory,
        "Component",
        {"Id": path_component_id, "Guid": "B8E82A46-9667-4570-806A-A07E7439FE13"},
    )
    ET.SubElement(
        path_component,
        "Environment",
        {
            "Id": "ApplicationPath",
            "Name": "PATH",
            "Value": "[INSTALLFOLDER]bin",
            "Action": "set",
            "Part": "last",
            "System": "yes",
            "Permanent": "no",
        },
    )
    ET.SubElement(
        path_component,
        "RegistryValue",
        {
            "Root": "HKLM",
            "Key": r"Software\AlgorithmLocalJudge",
            "Name": "InstallPathComponent",
            "Type": "integer",
            "Value": "1",
            "KeyPath": "yes",
        },
    )
    component_ids.append(path_component_id)
    feature = ET.SubElement(
        package,
        "Feature",
        {"Id": "MainFeature", "Title": "Algorithm Local Judge", "Level": "1"},
    )
    for component_id in component_ids:
        ET.SubElement(feature, "ComponentRef", {"Id": component_id})
    ET.indent(wix, space="  ")
    return ET.tostring(wix, encoding="unicode", xml_declaration=True) + "\n"


def build_msi(
    archive_path: Path,
    output_dir: Path,
    version: str,
    platform_id: str = SUPPORTED_PLATFORM,
) -> Path:
    validate_windows_platform(platform_id)
    wix = shutil.which("wix")
    if wix is None:
        raise ValueError("WiX Toolset v4 is required to build the MSI")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{PACKAGE_NAME}-{version}-windows-amd64.msi"
    with tempfile.TemporaryDirectory(prefix="alj-msi-build-") as tmp:
        temporary = Path(tmp)
        app_root = stage_windows_standalone(archive_path.resolve(), temporary / "stage")
        source = temporary / "algorithm-local-judge.wxs"
        source.write_text(wix_source(app_root, version), encoding="utf-8")
        result = subprocess.run(
            [wix, "build", "-arch", "x64", "-out", str(output), str(source)],
            text=True,
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        raise ValueError(f"WiX build failed: {(result.stderr or result.stdout).strip()}")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/installers"))
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--platform", default=SUPPORTED_PLATFORM)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = build_msi(args.archive, args.output_dir, args.version, args.platform)
    except (OSError, ValueError, JudgeError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"Built Windows MSI: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
