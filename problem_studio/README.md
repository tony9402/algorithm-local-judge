# Problem Studio 사용법

`problem-studio`는 문제 제작자용 웹 도구입니다. 문제 저장소를 열고, 문제 파일을 편집하고, 테스트 데이터와 솔루션 기대 결과를 검증한 뒤 `.aljpack` 문제 팩을 만듭니다.

최종 사용자는 저장소 루트의 [개인 설치 및 운영 안내](../INSTALL.md)에서 GitHub clone 후
설치 절차를 먼저 확인하세요. 이 문서는 Problem Studio의 workspace·Git·pack 제작
상세 사용법을 설명합니다.

명령 이름은 `problem_studio`가 아니라 하이픈을 쓰는 `problem-studio`입니다.

## 빠른 시작

문제 저장소를 clone해서 열려면:

```bash
problem-studio web start --clone owner/repo --branch main --workspace ./workspace
```

이 명령은 저장소를 `./workspace/problems/{repo명}` 아래에 clone하고, 해당 저장소를 바로 선택해 엽니다. 예를 들어 `owner/algorithm-package`는 `./workspace/problems/algorithm-package`에 받아옵니다.

공식 문제 저장소를 직접 수정하기보다, 연습용 fork나 개인 문제 저장소를 workspace에 연결하는 것을 권장합니다.

이미 있는 문제 저장소를 열려면:

```bash
problem-studio web start --workspace /path/to/algorithm-package
```

여러 문제 저장소를 한 workspace에서 관리하려면 다음 구조를 사용합니다.

```text
workspace/
  problems/
    algorithm-package/
      .git/
      problems/
        01/
          problem.json
    private-problems/
      .git/
      problems/
        alpha/
          problem.json
```

Problem Studio UI의 `저장소` selector에서 작업할 repository를 고르면, 문제 목록과 Git 작업이 그 저장소로 전환됩니다.

브라우저가 자동으로 열리지 않으면 `http://127.0.0.1:8775`로 접속하세요.

## 실행 옵션

```bash
problem-studio web start --workspace ./algorithm-package
problem-studio web start --clone owner/repo --branch main --workspace ./workspace
problem-studio web start --workspace ./workspace --repo algorithm-package
problem-studio web start --host 127.0.0.1 --port 8775 --no-open
problem-studio web status
problem-studio web stop
problem-studio web restart
```

`start`는 백그라운드에서 실행하고 PID와 로그 경로를 출력합니다. `restart`는 마지막으로
시작한 workspace, repository, host와 port를 그대로 사용합니다. 전면 실행이 필요하면
`start`를 생략하고 `problem-studio web`을 사용합니다.

- `--workspace`: 작업할 문제 저장소 폴더입니다. 기본값은 현재 폴더입니다.
- `--clone`: 실행 전에 GitHub 저장소나 Git URL을 `workspace/problems/{repo명}`으로 clone합니다.
- `--branch`: clone할 branch를 지정합니다.
- `--repo`: 이미 있는 `workspace/problems/{repo명}` 저장소를 선택해 시작합니다.
- `--repo-name`: clone 대상 local directory 이름을 직접 지정합니다.
- `--host`, `--port`: 서버 주소를 바꿉니다. 기본 주소는 `127.0.0.1:8775`입니다.
- `--no-open`: 브라우저 자동 실행을 끕니다.

## Docker 실행

서명된 공식 이미지를 먼저 준비한 뒤 Problem Studio를 백그라운드 컨테이너로 실행할 수
있습니다. `--workspace`의 호스트 디렉터리가 컨테이너 `/workspace`에 연결됩니다.

```bash
judge docker setup
problem-studio docker web start --workspace /path/to/algorithm-package --port 8775
problem-studio docker web status
problem-studio docker web restart
problem-studio docker web stop
```

`--port`는 컨테이너 웹 포트와 호스트 공개 포트에 같은 값을 적용합니다. 포트는
`0.0.0.0`에 공개되므로 `http://<호스트-IP>:8775`로도 접속할 수 있습니다. Docker의
Problem Studio는 연결된 작업공간을 읽고 쓸 수 있으므로 신뢰할 수 있는 네트워크와
방화벽에서만 실행하세요. 동작 인자를 생략한 `problem-studio docker web`은 전면 실행입니다.

## 기본 작업 흐름

1. 빈 workspace에서는 `첫 문제 만들기`, `저장소 추가`, `저장소 열기` 중
   하나를 선택합니다. 문제를 선택하기 전에는 편집과 삭제 기능이 숨겨집니다.
2. 문제 번호, 제목, 폴더, 버전, 기본 프로필, 실행 제한을 입력합니다.
3. `generator/cases.yml`, validator, checker, solution 파일을 편집합니다.
4. `Cases 검사`로 데이터 계획을 확인합니다.
5. `Sample 데이터 생성`과 validator 검사로 입력 데이터가 맞는지 확인합니다.
6. 솔루션 파일을 만들거나 업로드하고 기대 결과를 지정합니다.
7. `기대 결과 검증`으로 AC, WA, TLE 같은 기대 결과가 맞는지 확인합니다.
8. 필요하면 Stress 테스트로 generator 기반 임의 케이스에서 솔루션 기대 결과가 유지되는지 확인합니다.
9. `전체 테스트`를 실행합니다.
10. 전체 테스트를 통과하면 `.aljpack`을 빌드합니다.
11. 만든 pack을 `judge pack install`로 설치해 실제 채점 흐름에서 확인합니다.

## 화면별 기능

### 문제 정보

- 새 문제 생성
- 문제 번호 변경
- 제목, 폴더, 버전, 기본 프로필 수정
- 컴파일, 데이터 생성, 기준 정답, 사용자 코드 실행 제한 수정
- generator, cases YAML, validator, checker, 기준 정답 경로 확인
- 문제 삭제

문제 삭제는 실수를 막기 위해 확인 문구를 요구합니다.

### 데이터 생성

- `generator/cases.yml` 편집
- `cases.yml` 구조 검사
- sample 데이터 생성
- 전체 데이터 생성
- 오류 위치와 원인 확인

`cases.yml` 오류가 있으면 어떤 위치가 잘못되었는지 먼저 고치면 됩니다. 예를 들어 `profiles.hidden.cases`가 list가 아니면 해당 위치와 기대한 형태를 함께 보여줍니다.

### 데이터 검증

- validator 파일 편집
- 생성된 입력 데이터가 조건을 만족하는지 확인
- sample 또는 전체 프로필 기준 검증

### 채점기

- checker 파일 편집
- 기준 정답 파일 확인
- 문제 도구 컴파일

### 솔루션

- 솔루션 파일 생성
- 솔루션 파일 업로드
- 솔루션 이름 변경과 내용 수정
- 기대 결과 지정
- 전체 또는 변경된 솔루션 중심 검증
- mismatch가 나면 실패 케이스의 input, expected, actual, diff 확인
- generator case 기반 Stress 테스트 실행
- Stress mismatch의 input, expected, actual, diff 미리보기
- mismatch 케이스를 `cases.yml`에 fixed 또는 generator case로 추가

솔루션 파일은 C++, Python, PyPy, Java를 지원합니다. 파일명에는 기대 결과 토큰을 붙일 수 있습니다.

```text
main_solution.ac.cpp
wrong_solution.wa.py
slow_pypy_solution.pypy.tle.py
slow_solution.tle.java
```

주요 토큰은 `ac`, `wa`, `tle`, `mle`입니다. PyPy 솔루션은 `.pypy` marker를 기대 결과 토큰 앞에 둡니다. PyPy 실행 파일은 `ALJ_PYPY`로 지정하거나 PATH의 `pypy3`, `pypy`를 사용합니다.

### 검증/빌드

- 전체 테스트 실행
- 전체 테스트 통과 후 현재 문제 `.aljpack` 빌드
- pack ID와 검증 프로필 지정
- 빌드된 pack 다운로드
- 여러 문제를 선택해 workspace 전체 pack bulk build
- 현재 작업공간의 `dist/packs/*.aljpack` 생성물 전체 제거
- 오래 걸리는 검사/build job 진행 상태 확인, 취소, stale 작업 정리

Pack 빌드는 전체 테스트를 통과한 뒤 진행하는 흐름입니다. 실패한 상태에서는 먼저 실패 원인을 고치도록 안내합니다.
`생성된 문제 팩 모두 제거`는 빌드 산출물만 삭제하며 문제 소스와 Git 저장소는 유지합니다.

### Git

Problem Studio는 문제 저장소의 Git 작업을 도와줍니다.

- workspace 안의 여러 repository 중 하나를 선택
- GitHub repository clone 후 자동 연결
- 기존 repository 등록과 선택
- status 확인
- fetch
- fast-forward pull
- 허용된 문제 파일 commit
- push

Git 작업은 항상 현재 선택한 저장소 root에서만 실행됩니다. 새 구조에서는 이 root가 `workspace/problems/{repo명}`입니다. Commit 허용 범위는 선택 저장소 기준 `problems/**`와 `testlib.h`로 제한됩니다.

토큰은 저장하지 않습니다. Git credential manager나 SSH agent에 이미 설정된 인증을 그대로 사용합니다.

## 만든 pack을 judge에서 확인하기

Problem Studio에서 `.aljpack`을 만든 뒤 실제 채점 도구에 설치해 확인합니다.

```bash
judge pack verify path/to/problem-pack.aljpack
judge pack install path/to/problem-pack.aljpack
judge list
judge run --problem <problem-id> --profile sample path/to/main.cpp
```

이 단계까지 통과하면 사용자가 받는 채점 흐름에서도 문제를 실행할 수 있습니다.

## 워크스페이스에서 조심할 점

- Problem Studio는 workspace 파일을 직접 수정합니다.
- 작업 전 Git 상태를 확인하고 필요한 변경은 commit해 두는 것을 권장합니다.
- 파일 경로는 문제 폴더 내부 상대 경로만 허용됩니다.
- solution upload는 안전한 파일명과 지원 확장자만 허용됩니다.
- 외부 접근 가능한 host로 열면 파일 저장, build, generate, validate, Git write/fetch/pull/push 같은 위험 작업이 비활성화됩니다.
- `problem-studio web`에는 외부 host에서 쓰기 작업을 강제로 허용하는 옵션이 없습니다. 쓰기 작업이 필요한 경우 로컬 binding인 `127.0.0.1`, `localhost`, `::1`로 실행하세요.
- 대화상자는 열릴 때 이름과 설명이 보조 기술에 전달되고, 첫 입력으로
  초점이 이동하며, Tab 초점 순환과 Escape 닫기·열기 trigger 복귀를 지원합니다.
- 작업 이력은 `$ALJ_DATA_HOME/jobs/problem-studio.json`에 저장되며, 재시작 중이던
  작업은 자동 재실행하지 않고 명시적인 중단 실패로 복구됩니다.
- `/healthz`, `/readyz`, `/metrics`는 로컬 운영 상태를 제공합니다.

## 문제가 생겼을 때

- 브라우저가 열리지 않으면 `http://127.0.0.1:8775`로 직접 접속합니다.
- 컴파일러나 Java가 없다는 오류가 나면 `judge doctor`로 환경을 확인합니다.
- `testlib.h`가 없다는 경고가 보이면 workspace 상태를 확인하고, 문제 저장소가 공통 `testlib.h`를 참조할 수 있는 구조인지 확인합니다.
- `cases.yml` 오류는 `Cases 검사` 결과의 위치와 기대 형태를 먼저 봅니다.
- Pack 빌드가 막히면 `전체 테스트` 결과와 솔루션 기대 결과 검증 결과를 먼저 고칩니다.
- Git push가 안 되면 branch가 원격보다 뒤처졌는지, 인증이 Git credential manager나 SSH agent에 설정되어 있는지 확인합니다.

## 개발자/릴리스 확인용 검증 명령

Problem Studio 흐름을 로컬에서 확인하려면:

```bash
make e2e-install
make e2e-problem-studio
```

전체 릴리스 전 확인은 루트에서 실행합니다.

```bash
make release-ready
```
