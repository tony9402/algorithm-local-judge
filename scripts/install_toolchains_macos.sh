#!/usr/bin/env bash
# 패키지 스모크 검증과 로컬 개발에 필요한 macOS 도구 체인을 설치합니다.
# --run 없이 실행하면 실제 설치 대신 수행할 Homebrew 명령을 안내합니다.
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
