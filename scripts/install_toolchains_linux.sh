#!/usr/bin/env bash
# 패키지 스모크 검증과 로컬 CI 유사 환경에 필요한 Linux 도구 체인을 설치합니다.
# --run 없이 실행하면 실제 설치 대신 수행할 패키지 설치 명령을 안내합니다.
set -euo pipefail

if [[ "${1:-}" != "--run" ]]; then
  cat <<'EOF'
Dry run: Linux toolchain setup

Install with your distribution package manager:
- Debian/Ubuntu: sudo apt install build-essential openjdk-17-jdk python3 git
- Fedora: sudo dnf install gcc-c++ java-17-openjdk-devel python3 git
- Arch: sudo pacman -S base-devel jdk17-openjdk python git

This script does not run package-manager commands automatically.
EOF
  exit 0
fi

echo "No automatic Linux install is performed. Use the dry-run output above for your distribution."
