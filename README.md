# 로컬 알고리즘 채점기

내 컴퓨터에서 알고리즘 문제를 설치하고, C++/Python/Java 풀이 코드를 바로 채점하는 도구입니다.

## 빠른 시작

macOS/Linux:

```bash
tar -xzf algorithm-local-judge-0.1.0-macos-arm64.tar.gz
./algorithm-local-judge/bin/judge problem install tony9402/algorithm-package
./algorithm-local-judge/bin/judge web
```

Windows는 WSL Ubuntu 기준:

WSL Ubuntu 터미널을 열고 Linux와 같은 방식으로 실행합니다.

```bash
sudo apt update
sudo apt install -y build-essential openjdk-17-jdk python3 pypy3
tar -xzf algorithm-local-judge-0.1.0-linux-amd64.tar.gz
./algorithm-local-judge/bin/judge problem install tony9402/algorithm-package
./algorithm-local-judge/bin/judge web
```

브라우저가 자동으로 열리지 않으면 `http://127.0.0.1:8765`로 접속하세요. 화면에서 문제를 고르고, 소스 파일을 올리거나 코드를 붙여넣은 뒤 `Run Tests`를 누르면 됩니다.

## Docker로 실행하기

Ubuntu 기반 Docker 이미지로도 실행할 수 있습니다. 이미지에는 `judge`, `problem-studio`, C++/Java/Python/PyPy 제출 실행 도구가 함께 들어갑니다.

```bash
docker build -t algorithm-local-judge .
docker run --rm -it \
  -p 127.0.0.1:8765:8765 \
  -v alj-data:/data \
  algorithm-local-judge
```

브라우저에서 `http://127.0.0.1:8765`로 접속합니다. Docker 컨테이너는 외부 접속을 위해 내부에서 `0.0.0.0`에 bind하므로, host port는 위 예시처럼 `127.0.0.1`에만 publish하는 것을 권장합니다.

CLI만 실행할 수도 있습니다.

```bash
docker run --rm -it -v alj-data:/data algorithm-local-judge judge doctor
docker run --rm -it -v alj-data:/data algorithm-local-judge judge problem install tony9402/algorithm-package
```

로컬 제출 파일을 채점하려면 현재 폴더를 `/workspace`로 mount합니다.

```bash
docker run --rm -it \
  -v alj-data:/data \
  -v "$PWD:/workspace" \
  algorithm-local-judge \
  judge --problem <problem-id> --profile sample main.cpp
```

Docker 이미지와 공식 문제 패키지 전체 데이터 생성 흐름을 검증하려면 다음 통합 테스트를 실행합니다.

```bash
make e2e-docker
```

## 다운로드

프로젝트 release 페이지에서 내 OS에 맞는 standalone 압축 파일을 받습니다.

- Apple Silicon Mac: `algorithm-local-judge-0.1.0-macos-arm64.tar.gz`
- Intel Mac: `algorithm-local-judge-0.1.0-macos-amd64.tar.gz`
- Linux 64-bit: `algorithm-local-judge-0.1.0-linux-amd64.tar.gz`
- Windows: WSL Ubuntu 안에서 `algorithm-local-judge-0.1.0-linux-amd64.tar.gz`를 사용합니다.

압축을 풀면 실행 파일은 다음 위치에 있습니다.

```text
algorithm-local-judge/bin/judge
```

아래 예시는 macOS/Linux/WSL 기준으로 `./algorithm-local-judge/bin/judge`를 사용합니다.

## C++/Java/Python/PyPy 설치

채점기 실행 자체는 standalone 파일로 동작하지만, 제출 언어에 따라 로컬 도구가 필요합니다.

- C++ 제출: `g++`
- Java 제출: `javac`, `java`
- Python 제출: `python3` 또는 `python`
- PyPy 제출: `pypy3` 또는 `pypy`

### macOS

```bash
xcode-select --install
brew install --cask temurin@17
brew install python pypy3
```

명령별 설치 대상:

- `xcode-select --install`: C++ 제출 실행에 필요한 `g++`와 기본 개발 도구를 설치합니다.
- `brew install --cask temurin@17`: Java 제출 실행에 필요한 JDK, `javac`, `java`를 설치합니다.
- `brew install python pypy3`: Python 제출용 `python3`와 PyPy 제출용 `pypy3`를 설치합니다.

설치 확인:

```bash
g++ --version
javac -version
java -version
python3 --version
pypy3 --version
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y build-essential openjdk-17-jdk python3 pypy3
```

명령별 설치 대상:

- `sudo apt update`: Ubuntu/Debian 패키지 목록을 갱신합니다.
- `sudo apt install -y build-essential openjdk-17-jdk python3 pypy3`: C++ 제출용 `g++`, Java 제출용 `javac`/`java`, Python 제출용 `python3`, PyPy 제출용 `pypy3`를 설치합니다.

설치 확인:

```bash
g++ --version
javac -version
java -version
python3 --version
pypy3 --version
```

### Fedora

```bash
sudo dnf install gcc-c++ java-17-openjdk-devel python3 pypy
```

명령별 설치 대상:

- `sudo dnf install gcc-c++ java-17-openjdk-devel python3 pypy`: C++ 제출용 `g++`, Java 제출용 `javac`/`java`, Python 제출용 `python3`, PyPy 제출용 `pypy` 또는 `pypy3`를 설치합니다.

설치 확인:

```bash
g++ --version
javac -version
java -version
python3 --version
pypy3 --version || pypy --version
```

### Windows WSL

WSL Ubuntu 터미널을 열고, Ubuntu/Debian과 같은 명령으로 C++/Java/Python/PyPy 도구를 설치합니다.

```bash
sudo apt update
sudo apt install -y build-essential openjdk-17-jdk python3 pypy3
```

명령별 설치 대상:

- `sudo apt update`: WSL Ubuntu 패키지 목록을 갱신합니다.
- `sudo apt install -y build-essential openjdk-17-jdk python3 pypy3`: C++ 제출용 `g++`, Java 제출용 `javac`/`java`, Python 제출용 `python3`, PyPy 제출용 `pypy3`를 설치합니다.

Ubuntu 터미널에서 설치 확인:

```bash
g++ --version
javac -version
java -version
python3 --version
pypy3 --version
```

설치가 잘 되었는지 채점기에서도 확인할 수 있습니다.

```bash
./algorithm-local-judge/bin/judge doctor
./algorithm-local-judge/bin/judge doctor --verbose
```

Windows 사용자도 WSL Ubuntu 터미널에서 같은 `./algorithm-local-judge/bin/judge` 명령을 사용하면 됩니다.

## 웹으로 채점하기

```bash
./algorithm-local-judge/bin/judge web
```

기본 주소는 `http://127.0.0.1:8765`입니다. 브라우저 자동 실행 없이 서버만 띄우려면 `--no-open`을 붙입니다.

```bash
./algorithm-local-judge/bin/judge web --no-open
```

웹 화면에서는 다음 순서로 사용합니다.

1. `문제 팩 설치`에서 공식 저장소 또는 `.aljpack` 파일을 설치합니다.
2. 문제와 실행 프로필을 선택합니다.
3. 소스 파일을 업로드하거나 `Paste Code`에 코드를 붙여넣습니다.
4. `Run Tests`를 눌러 채점합니다.
5. 오답이면 `Input`, `Expected`, `Actual`, `Diff`에서 실패 케이스를 확인합니다.

웹에서 할 수 있는 일:

- 공식 GitHub release 문제 팩 다운로드 설치
- 로컬 `.aljpack` 파일 업로드 설치
- 문제 목록, 설치된 팩, 캐시 상태 확인
- sample 데이터 미리보기
- `cases.yml` 검사, 데이터 생성, 채점 실행
- 소스 파일 업로드, 드래그앤드롭, 코드 붙여넣기
- 최근 제출 소스 불러오기, 검색, 삭제
- 실시간 생성/채점 진행 상황 확인
- Accepted, Wrong Answer, Runtime Error, Time Limit 결과 확인
- 오답 케이스의 입력, 정답, 내 출력, diff 확인과 다운로드
- 캐시 정리

## CLI로 채점하기

공식 문제 저장소를 설치하고 목록을 확인합니다.

```bash
./algorithm-local-judge/bin/judge problem install tony9402/algorithm-package
./algorithm-local-judge/bin/judge list
```

sample 데이터를 미리 만들 수 있습니다. 이미 만든 데이터가 유효하면 캐시를 재사용합니다.

```bash
./algorithm-local-judge/bin/judge generate <problem-id> --profile sample
./algorithm-local-judge/bin/judge generate <problem-id> --profile sample --force
```

제출 파일을 채점합니다.

```bash
./algorithm-local-judge/bin/judge run --problem <problem-id> --profile sample path/to/main.cpp
./algorithm-local-judge/bin/judge --problem <problem-id> --profile sample path/to/main.py
./algorithm-local-judge/bin/judge --problem <problem-id> --profile sample path/to/Main.java
```

지원하는 제출 파일은 `.cpp`, `.cc`, `.cxx`, `.py`, `.java`입니다.

Python 실행 파일은 `ALJ_PYTHON`, Java 도구는 `ALJ_JAVAC`, `ALJ_JAVA` 환경 변수로 바꿀 수 있습니다.

## 오답 확인

오답이 나면 실행 결과에 `run-id`와 `case-id`가 표시됩니다.

```bash
./algorithm-local-judge/bin/judge show <run-id> <case-id>
./algorithm-local-judge/bin/judge show <run-id> <case-id> --input
./algorithm-local-judge/bin/judge show <run-id> <case-id> --expected
./algorithm-local-judge/bin/judge show <run-id> <case-id> --actual
./algorithm-local-judge/bin/judge diff <run-id> <case-id>
```

`show`는 입력, 기대 출력, 실제 출력을 보여주고, `diff`는 기대 출력과 실제 출력의 차이를 보여줍니다.

## cases.yml 확인

문제 데이터 계획 파일인 `cases.yml`을 채점 전에 검사할 수 있습니다.

```bash
./algorithm-local-judge/bin/judge cases compile <problem-id>
./algorithm-local-judge/bin/judge cases compile <problem-id> --profile hidden --expanded --max-preview 5
./algorithm-local-judge/bin/judge cases compile --file path/to/cases.yml --json
```

오류가 있으면 어느 위치가 잘못되었는지 진단을 출력합니다.

## 문제 팩 관리

공식 저장소 기본값은 `tony9402/algorithm-package`입니다. release에 현재 플랫폼용 `.aljpack` 파일이 있으면 그 파일을 설치하고, 없으면 저장소 archive의 `problems/` source package를 설치합니다.

```bash
./algorithm-local-judge/bin/judge problem install tony9402/algorithm-package
./algorithm-local-judge/bin/judge problem install https://github.com/tony9402/algorithm-package
./algorithm-local-judge/bin/judge problem install tony9402/algorithm-package --asset basic-1-macos-arm64.aljpack
./algorithm-local-judge/bin/judge problem install tony9402/algorithm-package --ref main
```

직접 받은 `.aljpack`도 설치하고 검증할 수 있습니다.

```bash
./algorithm-local-judge/bin/judge pack verify path/to/problem-pack.aljpack
./algorithm-local-judge/bin/judge pack install path/to/problem-pack.aljpack
./algorithm-local-judge/bin/judge pack list
./algorithm-local-judge/bin/judge pack remove <pack-id>
```

직접 URL로 `.aljpack`을 설치할 때는 SHA-256 checksum 또는 sidecar 검증이 필요합니다.

```bash
./algorithm-local-judge/bin/judge problem install https://example.com/basic.aljpack --checksum <sha256>
./algorithm-local-judge/bin/judge problem install https://example.com/basic.aljpack --checksum-url https://example.com/basic.aljpack.sha256
```

`--checksum` 또는 `--checksum-url`을 생략하면 `<url>.sha256` sidecar를 자동으로 찾고, sidecar도 없으면 설치하지 않습니다.

기본 trusted repository는 `tony9402/algorithm-package`입니다. 다른 저장소의 release pack을 신뢰하려면 명시적으로 추가합니다.

```bash
./algorithm-local-judge/bin/judge pack trust list
./algorithm-local-judge/bin/judge pack trust add owner/name
./algorithm-local-judge/bin/judge pack trust remove owner/name
```

## 캐시 관리

채점 데이터와 실행 결과는 캐시에 저장됩니다.

```bash
./algorithm-local-judge/bin/judge cache status
./algorithm-local-judge/bin/judge cache clear --problem <problem-id>
./algorithm-local-judge/bin/judge cache clear --problem <problem-id> --profile sample
./algorithm-local-judge/bin/judge cache clear --runs
./algorithm-local-judge/bin/judge cache clear --all --dry-run
./algorithm-local-judge/bin/judge cache clear --all --yes
```

먼저 `--dry-run`으로 지울 대상을 확인하는 것을 권장합니다.

## 보안 기본값

`judge web`은 내 컴퓨터에서 혼자 쓰는 로컬 도구를 기본 전제로 합니다.

- 기본 host는 `127.0.0.1`입니다.
- `judge web`을 `0.0.0.0` 같은 외부 접근 가능한 주소에 bind하면 run/generate/sample API는 기본 차단됩니다.
- 꼭 필요한 경우에만 `./algorithm-local-judge/bin/judge web --host 0.0.0.0 --allow-remote-run`을 사용하세요. 같은 네트워크 사용자가 내 컴퓨터에서 코드를 실행하게 만들 수 있으므로 권장하지 않습니다.
- pasted source text는 2 MiB, uploaded source file은 4 MiB, Web `.aljpack` upload는 200 MiB를 넘으면 거절됩니다.
- remote download는 200 MiB, archive extraction은 total 200 MiB, file 50 MiB, member 5000개 제한을 적용합니다.
- 신뢰하지 않는 `.aljpack`이나 저장소는 설치하지 마세요. 문제 도구와 제출 코드는 로컬에서 실행됩니다.

## 문제가 생겼을 때

- 브라우저가 열리지 않으면 `http://127.0.0.1:8765`로 직접 접속합니다.
- C++ 컴파일 오류가 나면 `g++ --version`과 `./algorithm-local-judge/bin/judge doctor`를 확인합니다.
- Java 컴파일 오류가 나면 `javac -version`, `java -version`, `./algorithm-local-judge/bin/judge doctor`를 확인합니다.
- 문제 목록이 비어 있으면 `./algorithm-local-judge/bin/judge problem install tony9402/algorithm-package`를 먼저 실행합니다.
- 오답 원인을 보려면 `show`와 `diff` 명령을 사용합니다.
- 캐시가 꼬인 것 같으면 `cache status`와 `cache clear --all --dry-run`으로 먼저 확인합니다.
