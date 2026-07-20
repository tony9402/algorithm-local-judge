#!/usr/bin/env bash
# 한국어 개인 설치 경로: checkout 안에 격리된 가상환경을 만들고 앱을 설치합니다.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
VENV_DIR="${ALJ_VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${ALJ_BOOTSTRAP_PYTHON:-}"
SKIP_CHECKS=0

usage() {
    cat <<'EOF'
사용법: ./install.sh [--python PATH] [--venv PATH] [--skip-checks]

현재 사용자용으로 Judge와 Problem Studio를 설치합니다.
  --python PATH  Python 3.11 이상 실행 파일을 명시합니다.
  --venv PATH    가상환경 위치를 바꿉니다(기본: 저장소/.venv).
  --skip-checks   설치 후 doctor 점검을 건너뜁니다(자동화용).

Judge 문제 팩·제출 기록은 저장소가 아닌 사용자 데이터 경로에 보존됩니다.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            [[ $# -ge 2 ]] || { echo "--python에는 경로가 필요합니다." >&2; exit 2; }
            PYTHON_BIN="$2"
            shift 2
            ;;
        --venv)
            [[ $# -ge 2 ]] || { echo "--venv에는 경로가 필요합니다." >&2; exit 2; }
            VENV_DIR="$2"
            shift 2
            ;;
        --skip-checks)
            SKIP_CHECKS=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "알 수 없는 옵션: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$VENV_DIR" != /* ]]; then
    VENV_DIR="$ROOT_DIR/$VENV_DIR"
fi

if [[ -z "$PYTHON_BIN" ]]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

if [[ -z "$PYTHON_BIN" ]] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python 3.11 이상이 필요합니다. Python을 설치한 뒤 다시 실행하세요." >&2
    exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    echo "Python 3.11 이상이 필요합니다: $($PYTHON_BIN --version 2>&1)" >&2
    exit 1
fi

install_with_pip() {
    echo "표준 Python 가상환경을 사용합니다: $VENV_DIR"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    fi
    if ! "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
        "$VENV_DIR/bin/python" -m ensurepip --upgrade
    fi
    if ! "$VENV_DIR/bin/python" -m pip install --disable-pip-version-check --upgrade pip; then
        echo "pip 자체를 설치하지 못했습니다. 네트워크 또는 사내 Python mirror를 확인하세요." >&2
        return 1
    fi
    if ! "$VENV_DIR/bin/python" -m pip install \
        --disable-pip-version-check --editable "$ROOT_DIR"; then
        echo "Python 의존성을 설치하지 못했습니다. 네트워크 또는 사내 Python mirror를 확인하세요." >&2
        return 1
    fi
}

if command -v uv >/dev/null 2>&1; then
    echo "uv 잠금 파일로 의존성을 설치합니다: $ROOT_DIR"
    if ! UV_PROJECT_ENVIRONMENT="$VENV_DIR" uv sync --frozen --no-dev --project "$ROOT_DIR"; then
        echo "uv 설치가 실패해 표준 Python 가상환경으로 다시 시도합니다." >&2
        install_with_pip
    fi
else
    install_with_pip
fi

JUDGE="$VENV_DIR/bin/judge"
STUDIO="$VENV_DIR/bin/problem-studio"
if [[ ! -x "$JUDGE" || ! -x "$STUDIO" ]]; then
    echo "실행 파일을 만들지 못했습니다. '$VENV_DIR'와 설치 로그를 확인하세요." >&2
    exit 1
fi

if [[ "$SKIP_CHECKS" -eq 0 ]]; then
    echo "설치 후 환경을 점검합니다(컴파일러가 없으면 경고로 표시됩니다)."
    "$JUDGE" doctor --verbose || {
        echo "doctor 실행에 실패했습니다. '$JUDGE doctor --verbose'를 다시 실행하세요." >&2
        exit 1
    }
fi

cat <<EOF

설치가 완료되었습니다.
  가상환경: $VENV_DIR
  Judge: $JUDGE
  Problem Studio: $STUDIO

다음 명령:
  $JUDGE web
  $STUDIO web
  $JUDGE doctor --verbose

문제 팩·제출 기록은 사용자 데이터 경로에 저장됩니다. 제거할 때도 데이터는
기본적으로 보존되며, 자세한 업데이트·롤백·제거 방법은 INSTALL.md를 참고하세요.
EOF
