#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--run" ]]; then
  cat <<'EOF'
Dry run: macOS toolchain setup

Required tools:
- C++ compiler: xcode-select --install
- Java compiler/runtime: install a JDK, then set ALJ_JAVAC/ALJ_JAVA if needed
- Python runtime: python3
- Git: xcode-select --install or install Git separately

Run with --run to start only the Xcode Command Line Tools installer prompt.
EOF
  exit 0
fi

xcode-select --install
