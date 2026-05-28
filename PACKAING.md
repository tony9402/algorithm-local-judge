# 패키징 가이드

이 문서는 사용자가 Python 설치 없이 `judge` 명령을 사용할 수 있도록 standalone 실행 파일과 problem pack을 만드는 방법을 정리한다.

현재 배포 방식은 다음을 기준으로 한다.

- Standalone 실행 파일은 Nuitka로 빌드한다.
- Standalone 배포물은 `tar.gz`로 압축한다.
- Problem pack은 실행 파일에 내장하지 않고 별도 `.aljpack`으로 배포한다.
- Release build는 GitHub Actions가 아니라 로컬 빌드 중심으로 진행한다.
- 지원 platform id는 `macos-arm64`, `macos-amd64`, `windows-amd64`, `linux-amd64`를 사용한다.
- Standalone 배포물에는 `THIRD_PARTY_NOTICES.md`를 포함한다.

## 1. 사전 준비

필요한 도구:

- Python 3.11 이상
- uv
- C++ compiler
- Nuitka

개발 의존성은 `pyproject.toml`과 `uv.lock`으로 관리한다.

```bash
uv sync --dev
```

현재 Python 3.14에서는 Nuitka가 experimental support 경고를 낼 수 있다. 안정적인 release build에서는 Python 3.13 기반 빌드도 확인하는 것을 권장한다.

## 2. 기본 검증

패키징 전에 코드 품질과 기본 테스트를 먼저 통과시킨다.

```bash
make lint
make format-check
make test
```

uv sandbox 문제가 있거나 로컬 `.venv`를 직접 쓰고 싶다면 다음처럼 실행할 수 있다.

```bash
make lint RUFF=.venv/bin/ruff
make format-check RUFF=.venv/bin/ruff
make test PYTHON=.venv/bin/python
```

## 3. Problem Pack 빌드

Standalone 실행 파일에는 문제 데이터를 내장하지 않는다. 문제 변경 때마다 실행 파일을 다시 빌드하지 않기 위해 `.aljpack`을 별도로 만든다.

기본 문제 pack 생성:

```bash
make -C problems build-pack PROBLEM=06 PACK_ID=basic
```

로컬 `.venv`를 직접 사용할 경우:

```bash
make -C problems build-pack PYTHON=.venv/bin/python PROBLEM=06 PACK_ID=basic
```

생성 위치:

```text
dist/packs/basic-1-macos-arm64.aljpack
dist/packs/basic-1-macos-arm64.aljpack.sha256
```

`PLATFORM`을 명시할 수도 있다.

```bash
make -C problems build-pack PROBLEM=06 PACK_ID=basic PLATFORM=macos-arm64
```

단, 현재 구현은 cross-platform build를 지원하지 않는다. `macos-amd64`, `windows-amd64`, `linux-amd64` artifact는 해당 platform의 로컬 환경에서 빌드해야 한다.

### 3.1 공식 Problem Pack 배포 정책

공식 문제 저장소 기본값은 `tony9402/algorithm-package`다. 다른 저장소를 사용해야 하는 배포자는 `ALJ_OFFICIAL_PACK_REPOSITORY=owner/name`으로 기본값을 바꾸거나, 사용자가 `judge problem install owner/name` 또는 Web UI의 Official Repository 입력을 사용하게 안내한다.

공식 설치 우선순위:

1. GitHub latest release에서 `.aljpack` asset을 찾는다.
2. 현재 platform id가 포함된 asset을 우선 선택한다.
3. 사용자가 asset 이름을 명시하면 정확히 일치하는 `.aljpack`만 설치한다.
4. `.aljpack` asset이 없고 사용자가 asset을 강제하지 않았다면 repository source archive를 받아 `problems/` source package로 설치한다.

권장 release asset 이름:

```text
<pack-id>-<version>-<platform-id>.aljpack
```

예:

```text
basic-1-macos-arm64.aljpack
basic-1-macos-amd64.aljpack
basic-1-linux-amd64.aljpack
basic-1-windows-amd64.aljpack
```

지원 platform id:

```text
macos-arm64
macos-amd64
linux-amd64
windows-amd64
```

배포자는 신뢰 가능한 release asset만 게시해야 하며, 사용자는 신뢰한 repository와 `.aljpack`만 설치해야 한다. 문제 generator, validator, checker, solution 검증 도구는 로컬에서 실행된다.

공식 `.aljpack` release asset은 checksum sidecar를 함께 게시해야 한다.

```text
basic-1-macos-arm64.aljpack
basic-1-macos-arm64.aljpack.sha256
```

기본 trusted owner는 `tony9402`다. 다른 repository에서 공식 pack을 설치해야 한다면 사용자가 먼저 명시적으로 신뢰 repository를 추가한다.

```bash
judge pack trust list
judge pack trust add owner/name
judge problem install owner/name
```

직접 HTTP(S) `.aljpack` URL 설치는 사용자가 URL을 명시적으로 신뢰한 파일 설치 경로로 취급한다. 이 경로는 GitHub release의 trusted repository/checksum sidecar 정책과 별도로 동작하므로, 공식 배포에는 direct URL 대신 trusted GitHub release asset과 `.sha256` sidecar를 사용한다.

`.aljpack` 서명 검증은 아직 구현하지 않는다. 이는 별도 후속 보안 작업으로 진행한다.

## 4. Problem Pack 검증

생성된 pack을 검증한다.

```bash
make pack-verify PACK=dist/packs/basic-1-macos-arm64.aljpack
```

직접 명령:

```bash
uv run judge pack verify dist/packs/basic-1-macos-arm64.aljpack
```

검증 항목:

- archive path traversal 여부
- `manifest.json` hash 일치 여부
- `.cpp`, `.hpp`, `.h` 등 source 포함 여부
- debug/object artifact 포함 여부
- precompiled tool 존재 여부

## 5. Standalone 실행 파일 빌드

Nuitka로 standalone 실행 파일을 빌드하고 `tar.gz` archive를 만든다.

```bash
make build-standalone PLATFORM=macos-arm64
```

로컬 `.venv`를 직접 사용할 경우:

```bash
make build-standalone PYTHON=.venv/bin/python PLATFORM=macos-arm64
```

내부적으로 다음 스크립트를 실행한다.

```bash
.venv/bin/python scripts/build_standalone.py --platform macos-arm64
```

생성 위치:

```text
dist/standalone/algorithm-local-judge-0.1.0-macos-arm64.tar.gz
```

빌드 staging directory:

```text
build/standalone/macos-arm64/algorithm-local-judge/
  bin/
    judge
    web/static/
  README.md
  THIRD_PARTY_NOTICES.md
  checksums.txt
```

Nuitka cache는 workspace 내부에 둔다.

```text
build/nuitka-cache/
```

## 6. Release Artifact 검사

Standalone archive와 problem pack을 release 전에 검사한다.

```bash
make release-check
```

로컬 `.venv`를 직접 사용할 경우:

```bash
make release-check PYTHON=.venv/bin/python
```

검사 대상:

```text
dist/standalone/*.tar.gz
dist/packs/*.aljpack
```

검사 항목:

- standalone archive에 `bin/judge` 또는 `bin/judge.exe`가 있는지
- `README.md`, `THIRD_PARTY_NOTICES.md`, `checksums.txt`가 있는지
- `checksums.txt`의 hash가 실제 파일과 일치하는지
- `.aljpack`의 manifest hash가 일치하는지
- `.aljpack.sha256` checksum sidecar가 있고 hash가 일치하는지
- standalone Web static asset이 포함되어 있는지
- 명시한 target platform의 artifact가 있는지
- 금지 파일이 포함되어 있지 않은지

금지 파일 예:

```text
*.cpp
*.cc
*.cxx
*.hpp
*.hh
*.hxx
*.h
*.py
*.pdb
*.dSYM
*.o
*.obj
*.a
*.lib
```

## 7. Standalone Smoke Test

빌드된 standalone binary를 직접 실행한다.

```bash
build/standalone/macos-arm64/algorithm-local-judge/bin/judge --help
```

Problem pack 설치:

```bash
build/standalone/macos-arm64/algorithm-local-judge/bin/judge \
  pack install dist/packs/basic-1-macos-arm64.aljpack
```

설치된 pack 확인:

```bash
build/standalone/macos-arm64/algorithm-local-judge/bin/judge pack list
build/standalone/macos-arm64/algorithm-local-judge/bin/judge list
```

테스트 데이터 생성:

```bash
build/standalone/macos-arm64/algorithm-local-judge/bin/judge \
  generate 06 --profile sample --force
```

제출 코드 채점:

```bash
build/standalone/macos-arm64/algorithm-local-judge/bin/judge \
  --problem 06 --profile sample problems/06/solutions/main_solution.ac.cpp
```

제출 파일은 C++(`.cpp`, `.cc`, `.cxx`), Python(`.py`), Java(`.java`)를 지원한다.

로컬 웹 UI 실행:

```bash
build/standalone/macos-arm64/algorithm-local-judge/bin/judge web
build/standalone/macos-arm64/algorithm-local-judge/bin/judge web --no-open
```

`judge web`은 기본적으로 브라우저를 함께 연다. 브라우저 자동 실행 없이 서버만 띄우려면 `--no-open`을 사용한다. 웹 UI는 기본적으로 `127.0.0.1:8765`에 bind되며, problem pack 파일 업로드 설치, 공식 GitHub release pack 다운로드 설치, 데이터 생성, 소스 파일 업로드 제출, 코드 붙여넣기 제출, 실시간 생성/채점 로그, 오답 데이터 확인, cache 삭제를 지원한다.

## 8. 독립 환경 검증

개발용 `problems/` 디렉터리에 의존하지 않는지 확인하려면 환경 변수를 임시 위치로 지정한다.

```bash
mkdir -p /tmp/alj-empty

ALJ_PROJECT_ROOT=/tmp/alj-empty \
ALJ_DATA_HOME=/tmp/alj-data \
ALJ_CACHE_HOME=/tmp/alj-cache \
build/standalone/macos-arm64/algorithm-local-judge/bin/judge \
  pack install dist/packs/basic-1-macos-arm64.aljpack
```

이후 같은 환경 변수로 실행한다.

```bash
ALJ_PROJECT_ROOT=/tmp/alj-empty \
ALJ_DATA_HOME=/tmp/alj-data \
ALJ_CACHE_HOME=/tmp/alj-cache \
build/standalone/macos-arm64/algorithm-local-judge/bin/judge list

ALJ_PROJECT_ROOT=/tmp/alj-empty \
ALJ_DATA_HOME=/tmp/alj-data \
ALJ_CACHE_HOME=/tmp/alj-cache \
build/standalone/macos-arm64/algorithm-local-judge/bin/judge generate 06 --profile sample
```

## 9. 전체 로컬 Release 순서

권장 release 순서:

```bash
make lint
make format-check
make test
make -C problems build-pack PROBLEM=06 PACK_ID=basic PLATFORM=macos-arm64
make build-standalone PLATFORM=macos-arm64
make release-check
```

특정 platform을 릴리즈 대상으로 검사하려면 다음처럼 명시한다.

```bash
uv run python scripts/scan_release_artifact.py \
  --require-platform-artifact \
  --target-platform macos-arm64
```

`.venv`를 직접 사용할 경우:

```bash
make lint RUFF=.venv/bin/ruff
make format-check RUFF=.venv/bin/ruff
make test PYTHON=.venv/bin/python
make -C problems build-pack PYTHON=.venv/bin/python PROBLEM=06 PACK_ID=basic PLATFORM=macos-arm64
make build-standalone PYTHON=.venv/bin/python PLATFORM=macos-arm64
make release-check PYTHON=.venv/bin/python
```

## 10. 배포물 전달

사용자에게 전달할 파일:

```text
dist/standalone/algorithm-local-judge-0.1.0-macos-arm64.tar.gz
dist/packs/basic-1-macos-arm64.aljpack
dist/packs/basic-1-macos-arm64.aljpack.sha256
```

사용자 설치 흐름:

```bash
tar -xzf algorithm-local-judge-0.1.0-macos-arm64.tar.gz
algorithm-local-judge/bin/judge pack install basic-1-macos-arm64.aljpack
algorithm-local-judge/bin/judge list
algorithm-local-judge/bin/judge --problem 06 --profile sample main.cpp
```

## 11. 배포된 패키지 사용 방법

이 섹션은 배포물을 받은 사용자를 위한 실행 방법이다.

사용자는 일반적으로 다음 두 파일을 받는다.

```text
algorithm-local-judge-0.1.0-macos-arm64.tar.gz
basic-1-macos-arm64.aljpack
```

Windows/Linux/macOS amd64 사용자는 자신의 platform에 맞는 archive와 `.aljpack`을 받아야 한다.

### 11.1 압축 해제

macOS/Linux:

```bash
tar -xzf algorithm-local-judge-0.1.0-macos-arm64.tar.gz
```

압축 해제 후 구조:

```text
algorithm-local-judge/
  bin/
    judge
  README.md
  THIRD_PARTY_NOTICES.md
  checksums.txt
```

Windows에서도 `tar` 명령을 사용할 수 있다.

```powershell
tar -xzf algorithm-local-judge-0.1.0-windows-amd64.tar.gz
```

Windows 실행 파일은 다음 위치에 있다.

```text
algorithm-local-judge/bin/judge.exe
```

### 11.2 실행 확인

macOS/Linux:

```bash
algorithm-local-judge/bin/judge --help
```

Windows PowerShell:

```powershell
.\algorithm-local-judge\bin\judge.exe --help
```

### 11.3 Problem Pack 설치

Problem pack은 처음 한 번 설치한다.

macOS/Linux:

```bash
algorithm-local-judge/bin/judge pack install basic-1-macos-arm64.aljpack
```

Windows PowerShell:

```powershell
.\algorithm-local-judge\bin\judge.exe pack install basic-1-windows-amd64.aljpack
```

설치된 pack 확인:

```bash
algorithm-local-judge/bin/judge pack list
```

설치된 문제 목록 확인:

```bash
algorithm-local-judge/bin/judge list
```

### 11.4 테스트 데이터 생성

특정 문제의 테스트 데이터를 미리 생성하려면 다음을 실행한다.

```bash
algorithm-local-judge/bin/judge generate 06 --profile sample
```

강제로 다시 생성하려면 `--force`를 붙인다.

```bash
algorithm-local-judge/bin/judge generate 06 --profile sample --force
```

### 11.5 코드 채점

사용자는 자신의 코드 파일 경로만 넣어 채점할 수 있다.

```bash
algorithm-local-judge/bin/judge --problem 06 --profile sample main.cpp
algorithm-local-judge/bin/judge --problem 06 --profile sample main.py
algorithm-local-judge/bin/judge --problem 06 --profile sample Main.java
```

명시적 `run` 명령도 사용할 수 있다.

```bash
algorithm-local-judge/bin/judge run --problem 06 --profile sample main.cpp
algorithm-local-judge/bin/judge run --problem 06 --profile sample main.py
algorithm-local-judge/bin/judge run --problem 06 --profile sample Main.java
```

언어별 요구사항:

- C++: standalone 패키지 실행 환경에 `g++`가 필요하다.
- Python: `ALJ_PYTHON` 환경 변수 또는 `python3`/`python` 명령이 필요하다.
- Java: `ALJ_JAVAC`, `ALJ_JAVA` 환경 변수 또는 `javac`/`java` 명령이 필요하다.

정답이면 다음과 비슷하게 출력된다.

```text
Accepted (2 case(s))
run: ...
```

오답이면 첫 번째 틀린 case와 확인 명령이 출력된다.

```text
Wrong Answer on case 001

View:
  python3 -m judge show <run-id> <case-id>
```

Standalone 사용자라면 안내된 `python3 -m judge` 대신 standalone 실행 파일을 사용하면 된다.

```bash
algorithm-local-judge/bin/judge show <run-id> <case-id>
```

### 11.5.1 웹 UI로 채점

터미널 명령이 익숙하지 않은 사용자는 로컬 웹 UI를 실행한다.

macOS/Linux:

```bash
algorithm-local-judge/bin/judge web
```

Windows PowerShell:

```powershell
.\algorithm-local-judge\bin\judge.exe web
```

`judge web`은 기본적으로 브라우저를 함께 연다. 브라우저가 자동으로 열리지 않으면 `http://127.0.0.1:8765`에 접속한다. 브라우저 자동 실행 없이 서버만 실행하려면 `--no-open`을 사용한다. 웹 UI에서는 소스 파일을 업로드하거나 소스 코드를 직접 붙여넣어 C++/Python/Java 제출을 채점할 수 있다. Generate 중에는 입력 생성, validator, answer 생성, self-check 단계가 표시되고, 채점 중에는 컴파일, 데이터 준비, case 실행 상태가 실시간 로그로 표시된다.

공식 문제 저장소는 기본값으로 `tony9402/algorithm-package`를 사용한다. release에 `.aljpack` asset이 있으면 pack으로 설치하고, 없으면 repository archive의 `problems/` source package를 설치한다. 다른 저장소를 기본값으로 사용하려면 다음처럼 실행한다.

```bash
ALJ_OFFICIAL_PACK_REPOSITORY=owner/name algorithm-local-judge/bin/judge web
```

### 11.6 틀린 데이터 확인

오답의 입력, 정답, 사용자 출력을 한 번에 본다.

```bash
algorithm-local-judge/bin/judge show <run-id> <case-id>
```

입력만 확인:

```bash
algorithm-local-judge/bin/judge show <run-id> <case-id> --input
```

정답만 확인:

```bash
algorithm-local-judge/bin/judge show <run-id> <case-id> --expected
```

사용자 출력만 확인:

```bash
algorithm-local-judge/bin/judge show <run-id> <case-id> --actual
```

정답과 사용자 출력의 diff 확인:

```bash
algorithm-local-judge/bin/judge diff <run-id> <case-id>
```

### 11.7 캐시 확인과 삭제

생성된 테스트 데이터와 채점 기록 cache 상태를 확인한다.

```bash
algorithm-local-judge/bin/judge cache status
```

삭제 전 미리 보기:

```bash
algorithm-local-judge/bin/judge cache clear --all --dry-run
```

전체 cache 삭제:

```bash
algorithm-local-judge/bin/judge cache clear --all --yes
```

특정 문제 cache만 삭제:

```bash
algorithm-local-judge/bin/judge cache clear --problem 06 --yes
```

채점 run 기록만 삭제:

```bash
algorithm-local-judge/bin/judge cache clear --runs --yes
```

### 11.8 Problem Pack 업데이트와 삭제

새 problem pack을 받았다면 다시 install 하면 된다.

```bash
algorithm-local-judge/bin/judge pack install basic-2-macos-arm64.aljpack
```

설치된 pack 삭제:

```bash
algorithm-local-judge/bin/judge pack remove basic
```

삭제 후 목록 확인:

```bash
algorithm-local-judge/bin/judge pack list
```

### 11.9 PATH 등록

매번 `algorithm-local-judge/bin/judge`를 입력하기 번거롭다면 `bin` 디렉터리를 PATH에 추가한다.

macOS/Linux 예시:

```bash
export PATH="$PWD/algorithm-local-judge/bin:$PATH"
judge --help
```

Windows PowerShell 예시:

```powershell
$env:Path = "$PWD\algorithm-local-judge\bin;$env:Path"
judge.exe --help
```

### 11.10 사용자 데이터 위치

기본적으로 problem pack과 cache는 사용자 홈 아래에 저장된다.

macOS/Linux:

```text
~/.local/share/algorithm-local-judge/problem-packs/
~/.cache/algorithm-local-judge/
```

Windows:

```text
%LOCALAPPDATA%/algorithm-local-judge/problem-packs/
%LOCALAPPDATA%/algorithm-local-judge/cache/
```

원하는 위치를 직접 지정할 수도 있다.

```bash
ALJ_DATA_HOME=/path/to/data \
ALJ_CACHE_HOME=/path/to/cache \
algorithm-local-judge/bin/judge list
```

## 12. 주의사항

- Problem pack은 실행 파일에 내장하지 않는다.
- 문제를 바꿀 때는 standalone을 다시 빌드하지 않고 `.aljpack`을 새로 배포한다.
- 현재 cross-platform build는 지원하지 않는다.
- 각 OS/architecture 산출물은 해당 환경에서 로컬 빌드한다.
- Nuitka standalone은 source 직접 노출을 줄이지만 리버싱을 완전히 막지는 않는다.
- 클라이언트 artifact에는 secret key나 숨겨야 하는 정책을 넣지 않는다.
