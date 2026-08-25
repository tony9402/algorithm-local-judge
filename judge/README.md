# judge 사용법

`judge`는 문제 팩을 설치하고, C++/Python/Java 풀이 코드를 로컬에서 채점하는 도구입니다. CLI와 웹 UI를 모두 제공합니다.

최종 사용자는 저장소 루트의 [개인 설치 및 운영 안내](../INSTALL.md)에서 GitHub clone 후
설치 절차를 먼저 확인하세요. 이 문서는 CLI 상세 사용법과 개발 환경을 설명합니다.

## 빠른 시작

최종 사용자는 저장소 루트에서 다음 설치 절차를 먼저 실행합니다.

```bash
git clone --depth 1 https://github.com/tony9402/algorithm-local-judge.git
cd algorithm-local-judge
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```

설치가 끝나면 `judge setup`으로 언어 도구와 Docker 상태를 진단할 수 있습니다.
설치·변경 없이 진단만 하려면 `judge setup --check-only --verbose`를
사용합니다. `uv`는 소스 개발자에게만 필요한 선택 사항이며 일반 설치에는 필요하지 않습니다.

`problem install`에서 저장소를 생략하면 기본 공식 저장소인 `tony9402/algorithm-package`를 사용합니다.

## 환경 점검

채점이 잘 안 되거나 컴파일러가 잡히지 않으면 먼저 진단합니다.

```bash
judge doctor
judge doctor --verbose
judge doctor --json
```

`doctor`는 Python, C++ 컴파일러, Java 컴파일러/런타임, Git, Docker CLI/daemon,
캐시 위치, 설치된 팩, 공식 문제 저장소 설정을 확인합니다.

## 웹 UI

```bash
judge web start
judge web stop
judge web restart
judge web start --no-open
judge web start --host 127.0.0.1 --port 8765
judge web start --debug
```

`start`는 백그라운드에서 실행하고 PID와 로그 경로를 출력합니다. 중복 시작은 거부되며,
`restart`는 마지막 `start`의 host와 port 설정을 재사용합니다. 전면 실행이 필요하면 동작
인자를 생략하고 `judge web`을 사용합니다.

웹 화면 사용 순서:

1. `문제 팩 설치`로 공식 문제 저장소나 `.aljpack` 파일을 설치합니다.
2. 문제와 실행 프로필을 선택합니다.
3. 파일을 업로드하거나 `Source Code`에 코드를 붙여넣습니다.
4. `예제 채점` 또는 `전체 채점`을 누릅니다.
5. 오답이면 `Input`, `Expected`, `Actual`, `Diff`를 확인합니다.

웹에서 할 수 있는 일:

- 공식 GitHub release 문제 팩 다운로드 설치
- 로컬 `.aljpack` 업로드 설치
- 문제, pack, cache 상태 확인
- sample case preview
- `cases.yml` 검사와 데이터 생성
- 소스 파일 업로드, 드래그앤드롭, 코드 붙여넣기
- 제출마다 독립적으로 보존되는 채점 기록 검색, 상세 결과 확인, 코드 재사용·삭제
- 현재 문제의 최근 제출 3개와 전체 제출 기록 필터·페이지 탐색
- 실시간 실행 로그와 진행 상태 확인
- 오답 artifact 확인, 복사, 다운로드
- 캐시 정리
- debug 모드에서 상세 로그 확인

## CLI 기본 흐름

공식 문제 저장소를 설치합니다.

```bash
judge problem install tony9402/algorithm-package
judge list
```

테스트 데이터를 만들거나 캐시를 재생성합니다.

```bash
judge generate <problem-id> --profile sample
judge generate <problem-id> --profile hidden --force
```

풀이 코드를 채점합니다.

```bash
judge run --problem <problem-id> --profile sample path/to/main.cpp
judge --problem <problem-id> --profile sample path/to/main.py
judge --problem <problem-id> --profile sample --language pypy path/to/main.py
judge --problem <problem-id> --profile sample path/to/Main.java
```

지원 확장자는 `.cpp`, `.cc`, `.cxx`, `.py`, `.java`입니다. PyPy는 `.py` 파일을 사용하며 `--language pypy`로 선택합니다. PyPy 실행 파일은 `ALJ_PYPY`로 지정하거나 PATH의 `pypy3`, `pypy`를 사용합니다.

## 오답 확인

오답이 나면 결과에 `run-id`와 `case-id`가 표시됩니다. 그 값으로 실패 케이스를 확인합니다.

```bash
judge show <run-id> <case-id>
judge show <run-id> <case-id> --input
judge show <run-id> <case-id> --expected
judge show <run-id> <case-id> --actual
judge diff <run-id> <case-id>
```

`show`는 입력, 기대 출력, 실제 출력을 보여주고, `diff`는 기대 출력과 실제 출력의 차이를 보여줍니다.

## cases.yml 검사

문제 데이터 계획을 채점 전에 검사할 수 있습니다.

```bash
judge cases compile <problem-id>
judge cases compile <problem-id> --profile hidden --expanded --max-preview 5
judge cases compile --file path/to/cases.yml --json
```

`--expanded`는 실제로 펼쳐질 케이스를 보여주고, `--max-preview`는 미리보기 개수를 제한합니다.

## 문제 팩 설치와 관리

공식 저장소 기본값은 `tony9402/algorithm-package`입니다. latest release의
`.aljpack`을 설치할 때는 SHA-256 체크섬과 Sigstore 게시자 identity를 모두
검증합니다. 서명이 없거나 일치하지 않으면 설치를 중단합니다. release pack이
없는 개발 저장소는 사용자가 신뢰한 source archive로 설치될 수 있습니다.

```bash
judge problem install
judge problem install tony9402/algorithm-package
judge problem install https://github.com/tony9402/algorithm-package
judge problem install tony9402/algorithm-package
judge problem install tony9402/algorithm-package --ref main
```

로컬 `.aljpack` 파일은 직접 검증하고 설치할 수 있습니다.

```bash
judge pack verify path/to/problem-pack.aljpack
judge pack install path/to/problem-pack.aljpack
judge pack list
judge pack remove <pack-id>
judge pack remove-all --confirm
```

웹 화면의 `문제 팩` 목록에서도 개별 팩 또는 모든 팩을 제거할 수 있습니다. 전체 제거는
제출 기록과 문제 소스를 보존하며 확인 문구를 요구합니다.

로컬 파일은 사용자가 직접 선택한 비공식 입력이므로 설치 결과에 서명 미검증
경고가 표시됩니다. 공식 release pack은 반드시 `.sha256`과 `.sigstore.json`
sidecar를 함께 게시해야 합니다.

고급 기능으로, 문제 제작자는 source 폴더에서 직접 pack을 만들 수도 있습니다. 일반 풀이자는 보통 Problem Studio에서 pack을 만들거나 이미 배포된 pack을 설치하면 됩니다.

```bash
judge pack build path/to/problem --pack-id basic --verify-profile hidden
```

직접 URL로 `.aljpack`을 설치할 때는 SHA-256 checksum 또는 sidecar 검증이 필요합니다.

```bash
judge problem install https://example.com/basic.aljpack --checksum <sha256>
judge problem install https://example.com/basic.aljpack --checksum-url https://example.com/basic.aljpack.sha256
```

`--checksum` 또는 `--checksum-url`을 생략하면 `<url>.sha256` sidecar를 자동으로 찾고, sidecar가 없거나 checksum이 맞지 않으면 설치를 중단합니다.

다른 GitHub 저장소의 release pack을 신뢰하려면 allowlist에 추가합니다.

```bash
judge pack trust list
judge pack trust add owner/name
judge pack trust remove owner/name
```

## 캐시 관리

```bash
judge cache status
judge cache clear --problem <problem-id>
judge cache clear --problem <problem-id> --profile sample
judge cache clear --runs
judge cache clear --all --dry-run
judge cache clear --all --yes
```

`--dry-run`은 실제 삭제 없이 지울 대상을 보여줍니다. 전체 삭제는 실수를 줄이기 위해 확인을 요구하며, 자동화에서는 `--yes`를 사용합니다.

캐시 정리는 run의 상세 산출물을 제거하지만 웹에서 제출한 코드와 결과 요약은 지우지 않습니다. 이 기록은 상단 `제출 기록`에서 별도로 관리하며, 실행 중인 제출은 완료 또는 취소되기 전까지 삭제할 수 없습니다. 이전 버전의 최근 소스 기록은 원본 파일을 옮기거나 지우지 않고 호환 기록으로 표시됩니다.

## 자주 쓰는 명령

```bash
judge --help
judge doctor
judge problem install tony9402/algorithm-package
judge list
judge generate <problem-id> --profile sample
judge run --problem <problem-id> --profile sample path/to/main.cpp
judge show <run-id> <case-id>
judge diff <run-id> <case-id>
judge cache status
judge web start
```

## 안전하게 사용하기

`judge web start`는 기본적으로 내 컴퓨터에서만 접속하는 `127.0.0.1`에 열립니다. 외부 접근 가능한 host에 열면 run/generate/sample API는 기본 차단됩니다.

host의 `--allow-remote-run`은 OS 격리를 제공하지 않으므로 권장하지 않습니다.
비신뢰 풀이를 실행할 때는 Docker Engine 28 이상과 Cosign을 준비한 뒤 서명된
공식 이미지를 사용하는 launcher를 실행합니다.

```bash
judge docker setup
judge docker web
```

이 경로는 host 경로와 Docker socket을 mount하지 않고, 인터넷과 host gateway가 차단된
internal network, read-only rootfs, non-root UID, capability/resource 제한을 강제합니다.
단, 현재 제출 프로세스와 web control plane은 하나의 container/UID를 공유하므로
다중 사용자 시험 서버용 보안 경계는 아닙니다.

web 상태는 `/healthz`, `/readyz`, `/metrics`에서 확인할 수 있고 응답의
`X-Request-ID`로 구조화 요청 로그를 연결할 수 있습니다. 작업 이력은
`$ALJ_DATA_HOME/jobs/judge.json`에 원자적으로 저장되며, 재시작 중이던 작업은
`중단됨`으로 명시적으로 복구됩니다.

웹 입력 크기와 원격 다운로드에는 기본 제한이 있습니다.

- pasted source text: 2 MiB
- uploaded source file: 4 MiB
- Web `.aljpack` upload: 200 MiB
- remote download: 200 MiB
- archive extraction: total 200 MiB, file 50 MiB, member 5000개

신뢰하지 않는 `.aljpack`이나 저장소는 설치하지 마세요. 문제 도구와 제출 코드는 로컬에서 실행됩니다.
