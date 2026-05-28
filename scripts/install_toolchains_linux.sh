#!/usr/bin/env bash
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
