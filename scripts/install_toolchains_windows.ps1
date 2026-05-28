# 패키지 스모크 검증과 로컬 개발에 필요한 Windows 도구 체인을 설치합니다.
# -Run 없이 실행하면 실제 설치 대신 수행할 winget 명령을 안내합니다.

param(
    [switch]$Run
)

if (-not $Run) {
    @"
Dry run: Windows toolchain setup

Recommended tools:
- C++ compiler: MSYS2/MinGW or Visual Studio Build Tools
- Java compiler/runtime: JDK 17 or newer
- Python runtime: Python 3
- Git: Git for Windows

This script does not install packages automatically. Install the tools above and
set ALJ_JAVAC or ALJ_JAVA if javac/java are not on PATH.
"@
    exit 0
}

Write-Output "No automatic Windows install is performed. Use the dry-run output for manual setup."
