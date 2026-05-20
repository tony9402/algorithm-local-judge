# 로컬 알고리즘 채점기

책과 로컬 학습 환경에서 사용할 수 있는 독립형 채점 패키지입니다.

이 저장소는 채점기 엔진, CLI, 로컬 웹 UI, 공통 `testlib.h`, 패키징 스크립트를 관리합니다. 문제 원본과 문제별 generator/checker/validator/solution은 별도 problem 저장소에서 관리하며, 이 저장소에는 포함하지 않습니다.

## 저장소 역할

- `judge`: 채점기 Python 패키지
- `judge web`: 로컬 웹 UI
- `commons`: 문제 데이터 생성을 위한 공용 스크립트
- `testlib.h`: 문제 generator, validator, checker에서 함께 쓰는 공통 헤더
- `scripts`: standalone 빌드와 release artifact 검사 스크립트
- `tests`: 채점기 엔진과 웹 API 테스트

문제 작성, `cases.yml`, 문제별 Makefile 사용법은 problem 저장소의 README에서 관리합니다. 로컬 개발 중에는 `problems/` 디렉터리를 옆에 둘 수 있지만, 이 디렉터리는 이 저장소에 커밋하지 않습니다.

## 개발 환경

개발 환경은 `uv`로 관리합니다.

```bash
uv sync
uv run judge --help
```

코드 컨벤션은 `ruff`로 확인합니다. 라인 최대 길이는 99입니다.

```bash
make lint
make format-check
make test
```

## CLI 사용

GitHub release에 올라간 problem pack은 쉬운 명령으로 설치할 수 있습니다.

```bash
uv run judge problem install tony9402/algorithm-modules
uv run judge problem install https://github.com/tony9402/algorithm-modules
```

설치된 problem pack을 기준으로 문제 목록을 확인하고 데이터를 생성할 수 있습니다.

```bash
uv run judge problem list
uv run judge generate <problem-id> --profile sample
```

사용자 코드는 문제 ID를 명시해서 채점합니다.

```bash
uv run judge --problem <problem-id> --profile sample path/to/main.cpp
uv run judge --problem <problem-id> --profile sample path/to/main.py
uv run judge --problem <problem-id> --profile sample path/to/Main.java
```

제출 파일은 C++(`.cpp`, `.cc`, `.cxx`), Python(`.py`), Java(`.java`)를 지원합니다. Python 제출은 `ALJ_PYTHON` 또는 `python3`/`python`, Java 제출은 `ALJ_JAVAC`/`ALJ_JAVA` 또는 `javac`/`java`를 사용합니다.

## 로컬 웹 UI

CLI가 익숙하지 않은 사용자는 로컬 웹 UI를 사용할 수 있습니다.

```bash
uv run judge web
uv run judge web --no-open
```

`judge web`은 기본적으로 브라우저를 함께 엽니다. 브라우저 자동 실행 없이 서버만 띄우려면 `--no-open`을 사용합니다. 기본 주소는 `http://127.0.0.1:8765`입니다. 웹 화면에서는 problem pack 파일 업로드 설치, 공식 GitHub release pack 다운로드 설치, 문제 목록 확인, 테스트 데이터 생성, 소스 파일 업로드 채점, 소스 코드 붙여넣기 채점, 실시간 생성/채점 로그, 오답 입력/정답/사용자 출력/diff 확인, cache 삭제를 할 수 있습니다.

공식 problem pack 저장소는 기본값으로 `tony9402/algorithm-modules`를 사용합니다. 다른 저장소를 기본값으로 쓰려면 `ALJ_OFFICIAL_PACK_REPOSITORY=owner/name` 환경 변수를 설정합니다.

## Makefile

루트 `Makefile`은 이 저장소가 관리하는 공통 judge 코드와 패키징 작업만 다룹니다.

```bash
make help
make web
make test
make lint
make format-check
make build-standalone PLATFORM=macos-arm64
make release-check
```

문제 생성, 문제 도구 컴파일, 문제 pack 빌드는 problem 저장소에서 실행합니다.

## Problem Pack

Standalone 실행 파일에는 문제 데이터를 내장하지 않습니다. 문제 변경 때마다 실행 파일을 다시 빌드하지 않기 위해 problem pack은 `.aljpack` 파일로 별도 배포합니다.

Problem pack 설치와 검증:

```bash
uv run judge problem install tony9402/algorithm-modules
uv run judge pack install path/to/problem-pack.aljpack
uv run judge pack verify path/to/problem-pack.aljpack
uv run judge pack list
```

Standalone 배포물과 problem pack을 만드는 자세한 절차는 [PACKAING.md](PACKAING.md)를 참고합니다.

## 주요 명령

```bash
uv run judge --help
uv run judge problem install tony9402/algorithm-modules
uv run judge list
uv run judge generate <problem-id> --profile sample
uv run judge run --problem <problem-id> --profile sample path/to/main.cpp
uv run judge show <run-id> <case-id>
uv run judge diff <run-id> <case-id>
uv run judge cache status
uv run judge cache clear --all --dry-run
uv run judge web
```

## 오답 확인

오답이 발생하면 첫 번째 틀린 케이스의 입력, 기대 출력, 실제 출력을 run artifact로 저장합니다.

```text
.judge-cache/runs/<run-id>/wrong/<case-id>.in
.judge-cache/runs/<run-id>/wrong/<case-id>.expected
.judge-cache/runs/<run-id>/wrong/<case-id>.actual
```

내용 확인:

```bash
uv run judge show <run-id> <case-id>
uv run judge diff <run-id> <case-id>
```

## 캐시 관리

```bash
uv run judge cache status
uv run judge cache clear --problem <problem-id>
uv run judge cache clear --runs
uv run judge cache clear --all --dry-run
uv run judge cache clear --all --yes
```

캐시 삭제 명령은 cache root 내부의 resolved path만 대상으로 삼습니다.
