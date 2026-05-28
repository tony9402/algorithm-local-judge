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
