# macOS 및 Linux 설치·운영 안내

이 저장소는 Judge와 Problem Studio를 제공합니다. 문제 콘텐츠는 별도 문제 저장소에서
관리하므로 설치 후 `judge problem install`로 받아야 합니다. Windows는 현재 이 설치
스크립트의 지원 범위가 아닙니다.

## 준비물

공통으로 Git과 Python 3.11 이상이 필요합니다. `uv`가 있으면 `uv.lock`을 사용하고,
없으면 표준 `venv`와 `pip`를 사용합니다.

### macOS

Apple의 [Command Line Tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools)와
Python을 준비합니다. Homebrew가 없다면 Python 3.11 이상을
[python.org](https://www.python.org/downloads/macos/)에서 설치해도 됩니다.

```bash
xcode-select --install
brew install python
```

### Linux

Ubuntu/Debian에서는 다음 패키지를 설치합니다.

```bash
sudo apt update
sudo apt install -y curl git python3 python3-venv build-essential
```

다른 배포판에서는 같은 도구를 해당 패키지 관리자로 설치하세요. Java나 PyPy 풀이를
채점하려면 `java`/`javac` 또는 `pypy3`도 추가해야 합니다.

## 설치

스크립트가 macOS와 Linux를 자동 판별하고 적절한 사용자 경로를 선택합니다.

### curl로 바로 설치

```bash
curl -fsSL https://raw.githubusercontent.com/tony9402/algorithm-local-judge/main/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
```

스크립트는 공식 저장소의 `main` branch를 임시 디렉터리에 clone해 설치한 뒤 정리합니다.
먼저 내용을 확인하려면 아래 clone 방식을 사용하세요.

### Git clone 후 설치

```bash
git clone https://github.com/tony9402/algorithm-local-judge.git
cd algorithm-local-judge
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```

기본 설치 경로는 다음과 같습니다.

| 운영체제 | 공용 사용자 런타임 | 명령 |
| --- | --- | --- |
| macOS | `~/Library/Application Support/algorithm-local-judge/runtime` | `~/.local/bin/judge`, `~/.local/bin/problem-studio` |
| Linux | `${XDG_DATA_HOME:-$HOME/.local/share}/algorithm-local-judge/runtime` | `~/.local/bin/judge`, `~/.local/bin/problem-studio` |

설치된 코드는 checkout에 의존하지 않아 어느 디렉터리에서든 실행할 수 있습니다.
`~/.local/bin`이 PATH에 없으면 `~/.bashrc`, `~/.zshrc` 또는 `~/.profile`에 한 번만
등록합니다. 설치 명령의 마지막 `export`는 현재 터미널에도 즉시 적용하기 위한 것입니다.

설치 대상은 항상 전용 Python 가상환경이어야 합니다. 기존 런타임의 Python이 3.11 미만이거나
`pyvenv.cfg`가 없는 직접 설치 환경이면 `uv`와 `pip`를 실행하지 않고 중단합니다. `uv`가
Python 호환성 오류를 반환해도 `pip` fallback을 시도하지 않습니다.

```text
./install.sh [--python PATH] [--install-dir PATH] [--bin-dir PATH] [--skip-checks]
```

- `--python PATH`: 자동 탐색 대신 사용할 Python 3.11 이상 실행 파일
- `--install-dir PATH`: 공용 사용자 런타임 위치
- `--bin-dir PATH`: 두 명령의 링크 위치
- `--skip-checks`: 설치 후 점검 생략(자동화용)

설치 결과를 확인합니다.

```bash
judge --version
problem-studio --version
judge doctor --verbose
```

## 문제 설치와 첫 실행

```bash
judge problem install tony9402/algorithm-package
judge list
judge web start
problem-studio web start
```

Judge와 Problem Studio는 기본적으로 loopback 주소에만 바인딩합니다. 브라우저가 자동으로
열리지 않으면 각각 `http://127.0.0.1:8765`, `http://127.0.0.1:8775`로 접속하세요.
백그라운드 서버는 각각 `judge web stop`, `problem-studio web stop`으로 종료하고
`restart`로 마지막 시작 설정을 유지한 채 다시 시작합니다. 시작 명령에 로그 경로가 표시됩니다.

## 제출 언어 도구체인

설치 스크립트는 시스템 컴파일러를 설치하지 않습니다.

| 언어 | 필요한 실행 파일 | 확인 명령 |
| --- | --- | --- |
| C++ | `g++` 또는 `clang++` | `g++ --version` 또는 `clang++ --version` |
| Java | `javac`, `java` | `javac -version`, `java -version` |
| Python | `python3` 또는 `python` | `python3 --version` |
| PyPy | `pypy3` 또는 `pypy` | `pypy3 --version` |

경로를 직접 지정하려면 `ALJ_CXX`, `ALJ_JAVAC`, `ALJ_JAVA`, `ALJ_PYTHON`, `ALJ_PYPY`
환경 변수를 사용합니다.

## 업데이트와 롤백

clone 방식은 저장소를 갱신한 뒤 다시 설치합니다.

```bash
git status --short
git pull --ff-only
./install.sh
```

curl 방식은 같은 curl 명령을 다시 실행합니다. 이전 버전으로 롤백하려면 별도 worktree에서
그 버전을 설치합니다.

```bash
git worktree add ../algorithm-local-judge-rollback <이전-태그-또는-커밋>
cd ../algorithm-local-judge-rollback
./install.sh
```

특정 tag의 curl 설치는 스크립트 URL과 `ALJ_INSTALL_REF`를 같은 tag로 고정합니다.

```bash
curl -fsSL https://raw.githubusercontent.com/tony9402/algorithm-local-judge/<tag>/install.sh | ALJ_INSTALL_REF=<tag> bash
```

## 제거와 데이터 보존

clone한 저장소에서는 제거 대상을 확인한 뒤 스크립트를 실행합니다.

```bash
./uninstall.sh --dry-run
./uninstall.sh
```

저장소가 없다면 공식 스크립트를 바로 실행할 수 있습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/tony9402/algorithm-local-judge/main/uninstall.sh | bash -s -- --yes
```

설치할 때 사용자 경로를 지정했다면 같은 경로를 전달합니다.

```bash
./uninstall.sh --install-dir PATH --bin-dir PATH
```

스크립트는 installer marker와 명령 링크 대상을 검증한 후 Judge, Problem Studio와 전용
Python 런타임만 제거합니다. 문제 팩과 제출 기록은 런타임과 분리되어 삭제되지 않습니다.
기본 데이터/캐시 경로는
macOS에서 `~/Library/Application Support/algorithm-local-judge`와
`~/Library/Caches/algorithm-local-judge`, Linux에서 XDG data/cache 경로입니다.
`ALJ_DATA_HOME`과 `ALJ_CACHE_HOME`을 지정했다면 해당 경로가 우선합니다. 데이터 경로를
직접 삭제하면 복구할 수 없으므로 먼저 백업하세요.

## 문제 해결

- `Python 3.11 이상이 필요합니다`: `python3 --version`을 확인하거나
  `./install.sh --python <실행-파일>`로 직접 지정합니다.
- 가상환경 생성 실패: Ubuntu/Debian은 `python3-venv`를 설치합니다.
- `pip` 또는 `uv` 실패: 네트워크, proxy, Python mirror 설정을 확인합니다.
- 컴파일러 `missing`: `judge doctor --verbose`에 표시된 도구체인을 설치합니다.
- `judge: command not found`: `export PATH="$HOME/.local/bin:$PATH"`를 실행하거나 새
  터미널을 엽니다.
- 웹이 열리지 않음: `judge web start --no-open`의 출력에 표시된 로그를 확인합니다.

## 개발·CI 검증

```bash
bash -n install.sh
python3 scripts/verify_install_docs.py
python3 -m unittest discover -s tests/install -p 'test_*.py' -v
```
