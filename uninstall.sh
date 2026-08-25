#!/usr/bin/env bash
# macOS/Linux 사용자 런타임과 installer가 만든 명령 링크만 안전하게 제거합니다.
set -euo pipefail

if [[ -z "${HOME:-}" ]]; then
    echo "사용자 설치 경로를 결정하려면 HOME 환경 변수가 필요합니다." >&2
    exit 1
fi

INSTALL_DIR="${ALJ_INSTALL_DIR:-}"
BIN_DIR="${ALJ_BIN_DIR:-$HOME/.local/bin}"
ASSUME_YES=0
DRY_RUN=0

usage() {
    cat <<'EOF'
사용법: ./uninstall.sh [--install-dir PATH] [--bin-dir PATH] [--yes] [--dry-run]

install.sh로 설치한 Judge와 Problem Studio 사용자 런타임을 제거합니다.
사용자 데이터인 문제 팩, 문제 소스, 제출 기록과 캐시는 삭제하지 않습니다.

  --install-dir PATH  기본 사용자 런타임 대신 제거할 설치 경로
  --bin-dir PATH      judge와 problem-studio 명령 링크가 있는 경로
  --yes               대화형 확인 없이 제거
  --dry-run           제거 대상을 표시하고 실제로 삭제하지 않음
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
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
        --yes)
            ASSUME_YES=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
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
        DATA_HOME="${ALJ_DATA_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/algorithm-local-judge}"
        CACHE_HOME="${ALJ_CACHE_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/algorithm-local-judge}"
        ;;
    Darwin)
        if [[ -z "$INSTALL_DIR" ]]; then
            INSTALL_DIR="$HOME/Library/Application Support/algorithm-local-judge/runtime"
        fi
        DATA_HOME="${ALJ_DATA_HOME:-$HOME/Library/Application Support/algorithm-local-judge}"
        CACHE_HOME="${ALJ_CACHE_HOME:-$HOME/Library/Caches/algorithm-local-judge}"
        ;;
    *)
        echo "현재 제거 스크립트는 macOS와 Linux만 지원합니다." >&2
        exit 1
        ;;
esac

normalize_target_path() {
    local path="$1"
    local parent
    local name
    if [[ "$path" != /* ]]; then
        path="$PWD/$path"
    fi
    parent="$(dirname -- "$path")"
    name="$(basename -- "$path")"
    if [[ "$name" == "." || "$name" == ".." ]]; then
        echo "안전하지 않은 제거 경로입니다: $path" >&2
        return 1
    fi
    if [[ -d "$parent" ]]; then
        parent="$(cd -- "$parent" && pwd -P)"
    fi
    printf '%s/%s\n' "$parent" "$name"
}

INSTALL_DIR="$(normalize_target_path "$INSTALL_DIR")"
BIN_DIR="$(normalize_target_path "$BIN_DIR")"
HOME_PHYSICAL="$(cd -- "$HOME" && pwd -P)"
if [[ "$INSTALL_DIR" == "/" || "$INSTALL_DIR" == "$HOME" ||
    "$INSTALL_DIR" == "$HOME_PHYSICAL" || "$BIN_DIR" == "/" ]]; then
    echo "안전하지 않은 제거 경로입니다." >&2
    exit 2
fi

MARKER="$INSTALL_DIR/.algorithm-local-judge-runtime"
if [[ -e "$INSTALL_DIR" ]]; then
    if [[ ! -f "$MARKER" ]] || [[ "$(<"$MARKER")" != "algorithm-local-judge user runtime" ]]; then
        echo "algorithm-local-judge가 만든 사용자 런타임이 아니므로 제거하지 않습니다: $INSTALL_DIR" >&2
        exit 1
    fi
    if [[ ! -f "$INSTALL_DIR/pyvenv.cfg" ]]; then
        echo "Python 가상환경 marker가 없어 제거하지 않습니다: $INSTALL_DIR" >&2
        exit 1
    fi
fi

command_names=(judge problem-studio)
owned_links=()
for command_name in "${command_names[@]}"; do
    command_path="$BIN_DIR/$command_name"
    command_target="$INSTALL_DIR/bin/$command_name"
    if [[ -L "$command_path" ]] && [[ "$(readlink -- "$command_path")" == "$command_target" ]]; then
        owned_links+=("$command_path")
    elif [[ -e "$command_path" || -L "$command_path" ]]; then
        echo "다른 설치가 관리하는 명령은 유지합니다: $command_path" >&2
    fi
done

echo "제거할 사용자 런타임: $INSTALL_DIR"
for command_path in "${owned_links[@]}"; do
    echo "제거할 명령 링크: $command_path"
done
echo "보존할 사용자 데이터: $DATA_HOME"
echo "보존할 캐시: $CACHE_HOME"

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "dry-run이므로 실제 파일은 제거하지 않았습니다."
    exit 0
fi

if [[ "$ASSUME_YES" -eq 0 ]]; then
    if [[ ! -t 0 ]]; then
        echo "대화형 입력을 사용할 수 없습니다. 검토 후 --yes를 지정하세요." >&2
        exit 1
    fi
    read -r -p 'Judge와 Problem Studio를 제거하려면 "제거"를 입력하세요: ' confirmation
    if [[ "$confirmation" != "제거" ]]; then
        echo "제거를 취소했습니다."
        exit 1
    fi
fi

service_names=(judge-web problem-studio-web)
for index in "${!command_names[@]}"; do
    service_state="$DATA_HOME/services/${service_names[$index]}.json"
    service_command="$INSTALL_DIR/bin/${command_names[$index]}"
    if [[ -f "$service_state" && -x "$service_command" ]]; then
        echo "백그라운드 서비스를 종료합니다: ${command_names[$index]} web"
        "$service_command" web stop
    fi
done

for command_path in "${owned_links[@]}"; do
    rm -f -- "$command_path"
done
if [[ -e "$INSTALL_DIR" ]]; then
    rm -rf -- "$INSTALL_DIR"
fi

echo "Judge와 Problem Studio 사용자 런타임을 제거했습니다."
echo "문제 팩, 문제 소스, 제출 기록과 캐시는 보존했습니다."
