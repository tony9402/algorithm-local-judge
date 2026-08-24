#!/usr/bin/env bash
# macOS/Linux 개인 설치 경로: checkout 밖의 공용 사용자 런타임에 앱을 설치합니다.
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [[ -n "$SCRIPT_PATH" ]]; then
    ROOT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" && pwd -P)"
else
    ROOT_DIR="$PWD"
fi
if [[ -z "${HOME:-}" ]]; then
    echo "사용자 설치 경로를 결정하려면 HOME 환경 변수가 필요합니다." >&2
    exit 1
fi
INSTALL_DIR="${ALJ_INSTALL_DIR:-}"
BIN_DIR="${ALJ_BIN_DIR:-}"
PYTHON_BIN="${ALJ_BOOTSTRAP_PYTHON:-}"
SKIP_CHECKS=0
PROFILE_FILE=""
INSTALL_ARGS=("$@")
BOOTSTRAP_DIR=""

usage() {
    cat <<'EOF'
사용법: ./install.sh [--python PATH] [--install-dir PATH] [--bin-dir PATH] [--skip-checks]

macOS 또는 Linux 현재 사용자용으로 Judge와 Problem Studio를 설치합니다.
  --python PATH       Python 3.11 이상 실행 파일을 명시합니다.
  --install-dir PATH  공용 사용자 런타임 위치를 바꿉니다.
  --bin-dir PATH      judge 명령 링크 위치를 바꿉니다.
  --skip-checks       설치 후 doctor 점검을 건너뜁니다(자동화용).

기본 런타임은 macOS의 ~/Library/Application Support 또는 Linux의
~/.local/share 아래에 설치하고, 명령은 ~/.local/bin에 등록합니다.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            [[ $# -ge 2 ]] || { echo "--python에는 경로가 필요합니다." >&2; exit 2; }
            PYTHON_BIN="$2"
            shift 2
            ;;
        --install-dir)
            [[ $# -ge 2 ]] || { echo "--install-dir에는 경로가 필요합니다." >&2; exit 2; }
            INSTALL_DIR="$2"
            shift 2
            ;;
        --bin-dir)
            [[ $# -ge 2 ]] || { echo "--bin-dir에는 경로가 필요합니다." >&2; exit 2; }
            BIN_DIR="$2"
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

case "$(uname -s)" in
    Linux)
        if [[ -z "$INSTALL_DIR" ]]; then
            DATA_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"
            INSTALL_DIR="$DATA_BASE/algorithm-local-judge/runtime"
        fi
        ;;
    Darwin)
        if [[ -z "$INSTALL_DIR" ]]; then
            INSTALL_DIR="$HOME/Library/Application Support/algorithm-local-judge/runtime"
        fi
        ;;
    *)
        echo "현재 설치 스크립트는 macOS와 Linux만 지원합니다." >&2
        echo "macOS 또는 Linux 환경에서 다시 실행하세요." >&2
        exit 1
        ;;
esac
if [[ -z "$BIN_DIR" ]]; then
    BIN_DIR="$HOME/.local/bin"
fi

is_source_checkout() {
    [[ -n "$SCRIPT_PATH" ]] &&
        [[ -f "$ROOT_DIR/pyproject.toml" ]] &&
        [[ -f "$ROOT_DIR/uv.lock" ]] &&
        [[ -f "$ROOT_DIR/testlib.h" ]] &&
        [[ -d "$ROOT_DIR/alj_core" ]] &&
        [[ -d "$ROOT_DIR/judge" ]] &&
        [[ -d "$ROOT_DIR/problem_studio" ]]
}

bootstrap_from_github() {
    local repository="${ALJ_INSTALL_REPOSITORY:-tony9402/algorithm-local-judge}"
    local ref="${ALJ_INSTALL_REF:-main}"
    local temporary
    local source_dir

    if [[ ! "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
        echo "ALJ_INSTALL_REPOSITORY는 owner/name 형식이어야 합니다: $repository" >&2
        return 2
    fi
    if [[ ! "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] ||
        [[ "$ref" == *..* ]] || [[ "$ref" == */ ]] || [[ "$ref" == *//* ]]; then
        echo "안전하지 않은 ALJ_INSTALL_REF 값입니다: $ref" >&2
        return 2
    fi
    if ! command -v git >/dev/null 2>&1; then
        echo "curl 설치를 계속하려면 Git이 필요합니다." >&2
        return 1
    fi

    temporary="$(mktemp -d "${TMPDIR:-/tmp}/alj-bootstrap.XXXXXX")"
    source_dir="$temporary/source"
    BOOTSTRAP_DIR="$temporary"
    cleanup_bootstrap() {
        if [[ -n "$BOOTSTRAP_DIR" ]]; then
            rm -rf -- "$BOOTSTRAP_DIR"
        fi
    }
    trap cleanup_bootstrap EXIT

    echo "공식 저장소에서 설치 소스를 준비합니다: $repository@$ref"
    if ! git clone --quiet --depth 1 --single-branch --branch "$ref" -- \
        "https://github.com/$repository.git" "$source_dir"; then
        echo "공식 저장소를 내려받지 못했습니다: $repository@$ref" >&2
        return 1
    fi
    bash "$source_dir/install.sh" "${INSTALL_ARGS[@]}"
}

if ! is_source_checkout; then
    if bootstrap_from_github; then
        exit 0
    else
        status=$?
        exit "$status"
    fi
fi

normalize_target_path() {
    local path="$1"
    local parent
    local name
    if [[ "$path" != /* ]]; then
        path="$PWD/$path"
    fi
    parent="$(dirname -- "$path")"
    name="$(basename -- "$path")"
    mkdir -p "$parent"
    parent="$(cd -- "$parent" && pwd -P)"
    printf '%s/%s\n' "$parent" "$name"
}

INSTALL_DIR="$(normalize_target_path "$INSTALL_DIR")"
BIN_DIR="$(normalize_target_path "$BIN_DIR")"
if [[ "$INSTALL_DIR" == "/" || "$BIN_DIR" == "/" ]]; then
    echo "설치 경로로 루트 디렉터리를 사용할 수 없습니다." >&2
    exit 2
fi
if [[ "$BIN_DIR" == *:* || "$BIN_DIR" == *$'\n'* ]]; then
    echo "명령 경로에는 콜론이나 줄바꿈을 사용할 수 없습니다: $BIN_DIR" >&2
    exit 2
fi

command_names=(judge problem-studio)
for command_name in "${command_names[@]}"; do
    command_path="$BIN_DIR/$command_name"
    command_target="$INSTALL_DIR/bin/$command_name"
    if [[ -L "$command_path" && "$(readlink -- "$command_path")" == "$command_target" ]]; then
        continue
    fi
    if [[ -e "$command_path" || -L "$command_path" ]]; then
        echo "기존 명령을 덮어쓰지 않습니다: $command_path" >&2
        exit 1
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    for candidate in python3 python python3.14 python3.13 python3.12 python3.11; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
                >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

if [[ -z "$PYTHON_BIN" ]]; then
    echo "Python 3.11 이상이 필요합니다. Python을 설치한 뒤 다시 실행하세요." >&2
    exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python 3.11 이상이 필요합니다. Python을 설치한 뒤 다시 실행하세요." >&2
    exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    echo "Python 3.11 이상이 필요합니다: $($PYTHON_BIN --version 2>&1)" >&2
    exit 1
fi

resolved_python="$(command -v "$PYTHON_BIN" 2>/dev/null || true)"
if [[ -n "$resolved_python" ]]; then
    PYTHON_BIN="$resolved_python"
fi
if [[ "$PYTHON_BIN" != /* ]]; then
    python_parent="$(cd -- "$(dirname -- "$PYTHON_BIN")" && pwd -P)"
    PYTHON_BIN="$python_parent/$(basename -- "$PYTHON_BIN")"
fi

python_is_supported() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
        >/dev/null 2>&1
}

python_is_venv() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)' \
        >/dev/null 2>&1
}

validate_runtime_venv() {
    local runtime_dir="$1"
    local label="$2"
    local runtime_python="$runtime_dir/bin/python"

    if [[ ! -f "$runtime_dir/pyvenv.cfg" || ! -x "$runtime_python" ]]; then
        echo "${label}이 Python 가상환경이 아닙니다: $runtime_dir" >&2
        echo "직접 설치 환경은 사용하지 않습니다. 다른 --install-dir을 지정하세요." >&2
        return 1
    fi
    if ! python_is_supported "$runtime_python"; then
        echo "${label}의 Python이 3.11 미만이므로 설치를 중단합니다: $($runtime_python --version 2>&1)" >&2
        echo "호환되는 새 경로를 --install-dir로 지정하거나 기존 런타임을 제거한 뒤 다시 실행하세요." >&2
        return 1
    fi
    if ! python_is_venv "$runtime_python"; then
        echo "${label}이 격리된 Python 가상환경으로 실행되지 않습니다: $runtime_dir" >&2
        echo "직접 설치 환경은 사용하지 않습니다. 다른 --install-dir을 지정하세요." >&2
        return 1
    fi
}

INSTALL_PYTHON="$PYTHON_BIN"
if [[ -e "$INSTALL_DIR" ]]; then
    validate_runtime_venv "$INSTALL_DIR" "기존 사용자 런타임" || exit 1
    INSTALL_PYTHON="$INSTALL_DIR/bin/python"
fi
mkdir -p "$BIN_DIR"

install_with_pip() {
    echo "표준 Python으로 사용자 런타임을 만듭니다: $INSTALL_DIR"
    if [[ -e "$INSTALL_DIR" && ! -f "$INSTALL_DIR/pyvenv.cfg" ]]; then
        echo "가상환경이 아닌 설치 경로에는 pip 설치를 진행하지 않습니다: $INSTALL_DIR" >&2
        return 1
    fi
    if [[ ! -f "$INSTALL_DIR/pyvenv.cfg" ]]; then
        if ! "$PYTHON_BIN" -m venv "$INSTALL_DIR"; then
            echo "Python 가상환경을 만들지 못했습니다." >&2
            echo "Ubuntu/Debian은 python3-venv 패키지를 설치한 뒤 다시 실행하세요." >&2
            return 1
        fi
    fi
    validate_runtime_venv "$INSTALL_DIR" "pip 설치 대상 런타임" || return 1
    if ! "$INSTALL_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
        "$INSTALL_DIR/bin/python" -m ensurepip --upgrade
    fi
    if ! "$INSTALL_DIR/bin/python" -m pip install --disable-pip-version-check --upgrade pip; then
        echo "pip 자체를 설치하지 못했습니다. 네트워크 또는 사내 Python mirror를 확인하세요." >&2
        return 1
    fi
    if ! "$INSTALL_DIR/bin/python" -m pip install \
        --disable-pip-version-check --upgrade "$ROOT_DIR"; then
        echo "Python 의존성을 설치하지 못했습니다. 네트워크 또는 사내 Python mirror를 확인하세요." >&2
        return 1
    fi
}

if command -v uv >/dev/null 2>&1; then
    echo "uv 잠금 파일로 사용자 런타임을 설치합니다: $INSTALL_DIR"
    uv_error_log="$(mktemp "${TMPDIR:-/tmp}/alj-uv-error.XXXXXX")"
    if UV_PROJECT_ENVIRONMENT="$INSTALL_DIR" uv sync --frozen --no-dev --no-editable \
        --python "$INSTALL_PYTHON" --project "$ROOT_DIR" 2>&1 | tee "$uv_error_log"; then
        rm -f -- "$uv_error_log"
    elif grep -Fq "incompatible with the project's Python requirement" "$uv_error_log"; then
        rm -f -- "$uv_error_log"
        echo "Python 버전이 프로젝트 요구사항과 맞지 않아 fallback 없이 설치를 중단합니다." >&2
        exit 1
    else
        rm -f -- "$uv_error_log"
        echo "uv 설치가 실패해 표준 Python 가상환경으로 다시 시도합니다." >&2
        install_with_pip
    fi
else
    install_with_pip
fi

validate_runtime_venv "$INSTALL_DIR" "설치된 사용자 런타임" || exit 1

JUDGE="$INSTALL_DIR/bin/judge"
STUDIO="$INSTALL_DIR/bin/problem-studio"
if [[ ! -x "$JUDGE" || ! -x "$STUDIO" ]]; then
    echo "실행 파일을 만들지 못했습니다. '$INSTALL_DIR'와 설치 로그를 확인하세요." >&2
    exit 1
fi

printf 'algorithm-local-judge user runtime\n' > "$INSTALL_DIR/.algorithm-local-judge-runtime"
cp "$ROOT_DIR/testlib.h" "$INSTALL_DIR/testlib.h"

for command_name in "${command_names[@]}"; do
    command_path="$BIN_DIR/$command_name"
    command_target="$INSTALL_DIR/bin/$command_name"
    if [[ ! -L "$command_path" ]]; then
        ln -s "$command_target" "$command_path"
    fi
done

select_profile_file() {
    if [[ -n "${ALJ_SHELL_PROFILE:-}" ]]; then
        printf '%s\n' "$ALJ_SHELL_PROFILE"
        return
    fi
    case "${SHELL##*/}" in
        bash) printf '%s/.bashrc\n' "$HOME" ;;
        zsh) printf '%s/.zshrc\n' "$HOME" ;;
        *) printf '%s/.profile\n' "$HOME" ;;
    esac
}

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        PROFILE_FILE="$(select_profile_file)"
        if [[ "$PROFILE_FILE" != /* ]]; then
            PROFILE_FILE="$PWD/$PROFILE_FILE"
        fi
        mkdir -p "$(dirname -- "$PROFILE_FILE")"
        touch "$PROFILE_FILE"
        printf -v quoted_bin_dir '%q' "$BIN_DIR"
        path_line="export PATH=${quoted_bin_dir}:\$PATH"
        if ! grep -Fqx -- "$path_line" "$PROFILE_FILE"; then
            printf '\n# Added by algorithm-local-judge installer.\n%s\n' "$path_line" >> "$PROFILE_FILE"
        fi
        ;;
esac

if [[ "$SKIP_CHECKS" -eq 0 ]]; then
    echo "설치 후 환경을 점검합니다(컴파일러가 없으면 경고로 표시됩니다)."
    "$JUDGE" doctor --verbose || {
        echo "doctor 실행에 실패했습니다. '$JUDGE doctor --verbose'를 다시 실행하세요." >&2
        exit 1
    }
fi

cat <<EOF

설치가 완료되었습니다.
  공용 사용자 런타임: $INSTALL_DIR
  Judge 명령: $BIN_DIR/judge
  Problem Studio 명령: $BIN_DIR/problem-studio

EOF

if [[ -n "$PROFILE_FILE" ]]; then
    printf '현재 터미널에 명령 경로를 적용하려면 한 번 실행하세요:\n  . %q\n\n' "$PROFILE_FILE"
fi

cat <<'EOF'
이후 어느 디렉터리에서든 다음처럼 실행할 수 있습니다.
  judge web
  problem-studio web
  judge doctor --verbose
  judge problem install tony9402/algorithm-package

문제 콘텐츠는 별도 문제 저장소에서 설치하며 이 도구 저장소에 포함되지 않습니다.
문제 팩·제출 기록은 사용자 데이터 경로에 저장됩니다. 제거할 때도 데이터는
기본적으로 보존되며, 자세한 업데이트·롤백·제거 방법은 INSTALL.md를 참고하세요.
EOF
