# 로컬 알고리즘 채점기

책과 로컬 학습 환경에서 사용할 수 있는 독립형 채점 패키지입니다. 문제별 전체 테스트 데이터를 저장소에 포함하지 않고, 문제별 생성 설정과 채점 도구로 필요한 데이터를 생성합니다.

## 기본 사용

개발 환경은 `uv`로 관리합니다.

```bash
uv sync
uv run judge --help
uv run judge cases compile 06 --profile sample
uv run judge generate 06 --profile sample
uv run judge --profile sample problems/06/solutions/main_solution.ac.cpp
```

사용자 코드가 문제 디렉터리 밖에 있으면 내부 문제 ID를 명시합니다.

```bash
uv run judge --problem 06 --profile sample path/to/main.cpp
uv run judge --problem 06 --profile sample path/to/main.py
uv run judge --problem 06 --profile sample path/to/Main.java
```

제출 파일은 C++(`.cpp`, `.cc`, `.cxx`), Python(`.py`), Java(`.java`)를 지원합니다. Python 제출은 `ALJ_PYTHON` 또는 `python3`/`python`, Java 제출은 `ALJ_JAVAC`/`ALJ_JAVA` 또는 `javac`/`java`를 사용합니다.

## 로컬 웹 UI

CLI가 익숙하지 않은 사용자는 로컬 웹 UI를 사용할 수 있습니다.

```bash
uv run judge web
uv run judge web --open
```

기본 주소는 `http://127.0.0.1:8765`입니다. 웹 화면에서는 problem pack 파일 업로드 설치, 공식 GitHub release pack 다운로드 설치, 문제 목록 확인, 테스트 데이터 생성, 소스 파일 업로드 채점, 소스 코드 붙여넣기 채점, 실시간 생성/채점 로그, 오답 입력/정답/사용자 출력/diff 확인, cache 삭제를 할 수 있습니다.

공식 problem pack 저장소는 기본값으로 `tony9402/algorithm-modules`를 사용합니다. 다른 저장소를 기본값으로 쓰려면 `ALJ_OFFICIAL_PACK_REPOSITORY=owner/name` 환경 변수를 설정합니다.

코드 컨벤션은 `ruff`로 확인합니다. 라인 최대 길이는 99입니다.

```bash
make lint
make format-check
```

## CLion에서 Make로 빌드

루트의 `Makefile`은 이 레포지토리가 유지하는 공통 judge 코드, `testlib.h`, standalone 패키징, pack 검증을 다룹니다. 실제 문제 소스는 이 레포지토리에 올리지 않고 별도 problem 저장소에서 관리하므로, 문제 생성/컴파일/pack 빌드는 `problems/Makefile`에서 실행합니다.

```bash
make help
make web
make test
```

문제 작업을 할 때는 로컬의 `problems/` 디렉터리에서 Makefile을 사용합니다. 이 디렉터리는 배포용 공통 레포지토리에 커밋하지 않습니다.

```bash
make -C problems help
make -C problems list-problems
make -C problems tools
make -C problems cases-compile
make -C problems generate
make -C problems run
```

자주 바꿀 변수:

```bash
make -C problems run PROBLEM=06 PROFILE=sample USER_SRC=path/to/main.cpp
make -C problems run PROBLEM=06 PROFILE=sample USER_SRC=path/to/main.py
make -C problems run PROBLEM=06 PROFILE=sample USER_SRC=path/to/Main.java
make -C problems cases-compile PROBLEM=06 PROFILE=sample
make -C problems generate PROBLEM=06 PROFILE=full
```

문제 번호 규칙을 확인하려면 다음을 실행합니다.

```bash
make -C problems validate-problems
```

문제 디렉터리는 숫자 ID를 사용하고, 번호는 1부터 연속이어야 합니다. 예를 들어 `01`, `02`, `03`, ... 형태로 30개 이상 존재할 수 있으며 상한은 두지 않습니다.

## 주요 명령

```bash
python3 -m judge compile 06
python3 -m judge cases compile 06 --profile sample
python3 -m judge cases compile --file problems/06/generator/cases.yml --profile sample
python3 -m judge list
python3 -m judge list --validate
python3 -m judge generate 06 --profile sample
python3 -m judge run --problem 06 --profile sample path/to/main.cpp
python3 -m judge run --problem 06 --profile sample path/to/main.py
python3 -m judge run --problem 06 --profile sample path/to/Main.java
python3 -m judge show <run-id> <case-id>
python3 -m judge diff <run-id> <case-id>
python3 -m judge cache status
python3 -m judge cache clear --all --dry-run
python3 -m judge web --open
```

## 문제 구조

```text
problems/<problemId>/
  problem.json
  generator/generator.cpp
  generator/cases.yml
  validator/validator.cpp
  checker/judge.cpp
  solutions/main_solution.ac.cpp
```

`problem.json`에는 내부 문제 ID와 로컬 채점에 필요한 도구 경로만 둡니다. 외부 플랫폼 식별자, 외부 URL, 외부 플랫폼명은 배포 파일에 포함하지 않습니다.

## 테스트 데이터 생성

`generator/generator.cpp`는 `testlib.h` 기반의 단일 입력 생성 도구입니다. 여러 케이스 구성은 문제별 `generator/cases.yml`에 선언하고, 공용 `commons/generate.py`가 YAML을 읽어 생성합니다.

YAML 예시:

```yaml
profiles:
  sample:
    cases:
      - name: min
        type: fixed
        content: |
          1 1
      - name: small-random
        type: generator
        seed: 1001
        args:
          minN: 1
          maxN: 4
          minM: 1
          maxM: 4
```

지원 케이스 타입:

- `fixed`: YAML에 적힌 입력을 그대로 사용
- `generator`: C++ generator를 seed와 args로 실행
- `template`: Python format style template에 `vars`를 적용

반복 케이스는 `repeat`로 줄일 수 있습니다.

```yaml
- repeat:
    var: i
    from: 1
    to: 20
    item:
      name: "stress-random-${i:02d}"
      type: generator
      seed: "${4000 + i}"
      args:
        minN: 1
        maxN: 8
        minM: 1
        maxM: 8
```

여러 축의 조합은 `matrix`를 사용합니다.

```yaml
- matrix:
    vars:
      n:
        range:
          from: 1
          to: 100
      m:
        range:
          from: 1
          to: 100
          step: 5
    where: "m <= n"
    item:
      name: "n-${n:03d}-m-${m:03d}"
      type: generator
      seed: "${100000 + n * 1000 + m}"
      args:
        minN: "${n}"
        maxN: "${n}"
        minM: "${m}"
        maxM: "${m}"
```

`matrix.vars`에는 기존처럼 `[1, 2, 3]` 형태의 명시 리스트도 사용할 수 있고, 위처럼 `range`로 범위를 줄 수도 있습니다. `range`는 `from`, `to`, `step`을 지원하며 `to` 값을 포함합니다.

### cases.yml 컴파일 검증

데이터를 실제로 생성하기 전에 `cases.yml`만 먼저 컴파일해서 YAML 구조, DSL 확장, 표현식, 케이스 schema 오류를 확인할 수 있습니다.

```bash
python3 -m judge cases compile 06 --profile sample
python3 -m judge cases compile 06 --profile sample --expanded --max-preview 20
python3 -m judge cases compile --file problems/06/generator/cases.yml --profile sample --json
```

오류 예시:

```text
cases.yml: invalid

problems/06/generator/cases.yml:14
  profile hidden, cases[0].matrix
  matrix must be a mapping, got null

hint:
  `vars`, `where`, and `item` must be indented under `matrix:`.
```

`judge generate`와 `judge run`도 내부적으로 먼저 같은 컴파일 검증을 수행합니다. 오류가 있으면 generator 빌드, 데이터 생성, 사용자 코드 컴파일로 넘어가지 않고 진단 메시지로 중단합니다. 웹 UI에서는 `Compile Cases` 버튼으로 직접 확인할 수 있고, `Generate`와 `Run`도 실행 전에 같은 검증을 거칩니다.

생성된 데이터는 `.judge-cache/problems/<problemId>/<generation-key>/` 아래에 저장됩니다. 같은 문제 버전, profile, 생성 스크립트, 도구 소스가 유지되면 캐시를 재사용합니다.

## 오답 확인

오답이 발생하면 첫 번째 틀린 케이스의 입력, 기대 출력, 실제 출력을 run artifact로 저장합니다.

```text
.judge-cache/runs/<run-id>/wrong/<case-id>.in
.judge-cache/runs/<run-id>/wrong/<case-id>.expected
.judge-cache/runs/<run-id>/wrong/<case-id>.actual
```

내용 확인:

```bash
python3 -m judge show <run-id> <case-id>
python3 -m judge diff <run-id> <case-id>
```

## 캐시 관리

```bash
python3 -m judge cache status
python3 -m judge cache clear --problem 06
python3 -m judge cache clear --runs
python3 -m judge cache clear --all --dry-run
python3 -m judge cache clear --all --yes
```

캐시 삭제 명령은 `.judge-cache` 내부의 resolved path만 대상으로 삼습니다.

## 현재 포함된 내부 문제

- `06`: 순열 기본
