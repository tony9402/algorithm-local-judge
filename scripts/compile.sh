#!/usr/bin/env sh
# 기존 scripts/compile.sh 진입점을 유지하면서 실제 컴파일 동작은 judge compile 명령에 위임합니다.
# Makefile과 배포 스크립트가 같은 명령 경로를 사용하도록 이 래퍼를 보존합니다.
set -eu

python3 -m judge compile "$@"
