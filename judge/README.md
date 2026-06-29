# judge 사용법

`judge`는 문제 팩을 설치하고, C++/Python/Java 풀이 코드를 로컬에서 채점하는 도구입니다. CLI와 웹 UI를 모두 제공합니다.

## 빠른 시작

```bash
uv sync
uv run judge problem install tony9402/algorithm-package
uv run judge web
```

브라우저가 자동으로 열리지 않으면 `http://127.0.0.1:8765`로 접속하세요. 이미 설치된 실행 파일을 쓰는 경우에는 `uv run`을 빼고 `judge web`처럼 실행하면 됩니다.

`uv`가 없다면 [uv 공식 설치 문서](https://docs.astral.sh/uv/)를 참고해 먼저 설치하세요.

`problem install`에서 저장소를 생략하면 기본 공식 저장소인 `tony9402/algorithm-package`를 사용합니다.

## 환경 점검

채점이 잘 안 되거나 컴파일러가 잡히지 않으면 먼저 진단합니다.

```bash
uv run judge doctor
uv run judge doctor --verbose
uv run judge doctor --json
```

`doctor`는 Python, C++ 컴파일러, Java 컴파일러/런타임, Git, 캐시 위치, 설치된 팩, 공식 문제 저장소 설정을 확인합니다.

## 웹 UI

```bash
uv run judge web
uv run judge web --no-open
uv run judge web --host 127.0.0.1 --port 8765
uv run judge web --debug
```

웹 화면 사용 순서:

1. `문제 팩 설치`로 공식 문제 저장소나 `.aljpack` 파일을 설치합니다.
2. 문제와 실행 프로필을 선택합니다.
3. 파일을 업로드하거나 코드를 붙여넣습니다.
4. `Run Tests`를 누릅니다.
5. 오답이면 `Input`, `Expected`, `Actual`, `Diff`를 확인합니다.

웹에서 할 수 있는 일:

- 공식 GitHub release 문제 팩 다운로드 설치
- 로컬 `.aljpack` 업로드 설치
- 문제, pack, cache 상태 확인
- sample case preview
- `cases.yml` 검사와 데이터 생성
- 소스 파일 업로드, 드래그앤드롭, 코드 붙여넣기
- 최근 제출 소스 검색, 재사용, 삭제
- 실시간 실행 로그와 진행 상태 확인
- 오답 artifact 확인, 복사, 다운로드
- 캐시 정리
- debug 모드에서 상세 로그 확인

## CLI 기본 흐름

공식 문제 저장소를 설치합니다.

```bash
uv run judge problem install tony9402/algorithm-package
uv run judge list
```

테스트 데이터를 만들거나 캐시를 재생성합니다.

```bash
uv run judge generate <problem-id> --profile sample
uv run judge generate <problem-id> --profile hidden --force
```

풀이 코드를 채점합니다.

```bash
uv run judge run --problem <problem-id> --profile sample path/to/main.cpp
uv run judge --problem <problem-id> --profile sample path/to/main.py
uv run judge --problem <problem-id> --profile sample --language pypy path/to/main.py
uv run judge --problem <problem-id> --profile sample path/to/Main.java
```

지원 확장자는 `.cpp`, `.cc`, `.cxx`, `.py`, `.java`입니다. PyPy는 `.py` 파일을 사용하며 `--language pypy`로 선택합니다. PyPy 실행 파일은 `ALJ_PYPY`로 지정하거나 PATH의 `pypy3`, `pypy`를 사용합니다.

## 오답 확인

오답이 나면 결과에 `run-id`와 `case-id`가 표시됩니다. 그 값으로 실패 케이스를 확인합니다.

```bash
uv run judge show <run-id> <case-id>
uv run judge show <run-id> <case-id> --input
uv run judge show <run-id> <case-id> --expected
uv run judge show <run-id> <case-id> --actual
uv run judge diff <run-id> <case-id>
```

`show`는 입력, 기대 출력, 실제 출력을 보여주고, `diff`는 기대 출력과 실제 출력의 차이를 보여줍니다.

## cases.yml 검사

문제 데이터 계획을 채점 전에 검사할 수 있습니다.

```bash
uv run judge cases compile <problem-id>
uv run judge cases compile <problem-id> --profile hidden --expanded --max-preview 5
uv run judge cases compile --file path/to/cases.yml --json
```

`--expanded`는 실제로 펼쳐질 케이스를 보여주고, `--max-preview`는 미리보기 개수를 제한합니다.

## 문제 팩 설치와 관리

공식 저장소 기본값은 `tony9402/algorithm-package`입니다. latest release에 현재 플랫폼용 `.aljpack` asset이 있으면 checksum sidecar를 검증한 뒤 pack으로 설치하고, asset이 없으면 repository archive의 `problems/` source package를 설치합니다.

```bash
uv run judge problem install
uv run judge problem install tony9402/algorithm-package
uv run judge problem install https://github.com/tony9402/algorithm-package
uv run judge problem install tony9402/algorithm-package --asset basic-1-macos-arm64.aljpack
uv run judge problem install tony9402/algorithm-package --ref main
```

로컬 `.aljpack` 파일은 직접 검증하고 설치할 수 있습니다.

```bash
uv run judge pack verify path/to/problem-pack.aljpack
uv run judge pack install path/to/problem-pack.aljpack
uv run judge pack list
uv run judge pack remove <pack-id>
```

고급 기능으로, 문제 제작자는 source 폴더에서 직접 pack을 만들 수도 있습니다. 일반 풀이자는 보통 Problem Studio에서 pack을 만들거나 이미 배포된 pack을 설치하면 됩니다.

```bash
uv run judge pack build path/to/problem --pack-id basic --verify-profile hidden
```

직접 URL로 `.aljpack`을 설치할 때는 SHA-256 checksum 또는 sidecar 검증이 필요합니다.

```bash
uv run judge problem install https://example.com/basic.aljpack --checksum <sha256>
uv run judge problem install https://example.com/basic.aljpack --checksum-url https://example.com/basic.aljpack.sha256
```

`--checksum` 또는 `--checksum-url`을 생략하면 `<url>.sha256` sidecar를 자동으로 찾고, sidecar가 없거나 checksum이 맞지 않으면 설치를 중단합니다.

다른 GitHub 저장소의 release pack을 신뢰하려면 allowlist에 추가합니다.

```bash
uv run judge pack trust list
uv run judge pack trust add owner/name
uv run judge pack trust remove owner/name
```

## 캐시 관리

```bash
uv run judge cache status
uv run judge cache clear --problem <problem-id>
uv run judge cache clear --problem <problem-id> --profile sample
uv run judge cache clear --runs
uv run judge cache clear --all --dry-run
uv run judge cache clear --all --yes
```

`--dry-run`은 실제 삭제 없이 지울 대상을 보여줍니다. 전체 삭제는 실수를 줄이기 위해 확인을 요구하며, 자동화에서는 `--yes`를 사용합니다.

## 자주 쓰는 명령

```bash
uv run judge --help
uv run judge doctor
uv run judge problem install tony9402/algorithm-package
uv run judge list
uv run judge generate <problem-id> --profile sample
uv run judge run --problem <problem-id> --profile sample path/to/main.cpp
uv run judge show <run-id> <case-id>
uv run judge diff <run-id> <case-id>
uv run judge cache status
uv run judge web
```

## 안전하게 사용하기

`judge web`은 기본적으로 내 컴퓨터에서만 접속하는 `127.0.0.1`에 열립니다. 외부 접근 가능한 host에 열면 run/generate/sample API는 기본 차단됩니다.

```bash
uv run judge web --host 0.0.0.0 --allow-remote-run
```

위 옵션은 같은 네트워크의 다른 사용자가 내 컴퓨터에서 코드를 실행하게 만들 수 있으므로 꼭 필요한 경우에만 사용하세요.

웹 입력 크기와 원격 다운로드에는 기본 제한이 있습니다.

- pasted source text: 2 MiB
- uploaded source file: 4 MiB
- Web `.aljpack` upload: 200 MiB
- remote download: 200 MiB
- archive extraction: total 200 MiB, file 50 MiB, member 5000개

신뢰하지 않는 `.aljpack`이나 저장소는 설치하지 마세요. 문제 도구와 제출 코드는 로컬에서 실행됩니다.
