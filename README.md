# 로컬 알고리즘 채점기

알고리즘 문제를 설치하고 C++, Python, PyPy, Java 풀이를 내 컴퓨터에서 채점하는
도구입니다. 풀이 채점용 Judge와 문제 제작용 Problem Studio를 함께 제공합니다.

## macOS 설치

Git과 C++ 컴파일러는 [Command Line Tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools)로,
Python 3.11 이상은 [Homebrew](https://formulae.brew.sh/formula/python)로 준비합니다.

```bash
xcode-select --install
brew install python
```

curl로 바로 설치합니다.

```bash
curl -fsSL https://raw.githubusercontent.com/tony9402/algorithm-local-judge/main/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
```

소스를 확인하고 설치하려면 다음 방법을 사용합니다.

<!-- alj-install:start os=macos -->
```bash
git clone https://github.com/tony9402/algorithm-local-judge.git
cd algorithm-local-judge
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```
<!-- alj-install:end os=macos -->

프로그램은 `~/Library/Application Support/algorithm-local-judge/runtime`에 설치되고,
`judge`와 `problem-studio`는 `~/.local/bin`에 등록됩니다.

## Linux 설치

Ubuntu/Debian에서는 필요한 패키지를 먼저 준비합니다.

```bash
sudo apt update
sudo apt install -y curl git python3 python3-venv build-essential
```

curl로 바로 설치합니다.

```bash
curl -fsSL https://raw.githubusercontent.com/tony9402/algorithm-local-judge/main/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
```

소스를 확인하고 설치하려면 다음 방법을 사용합니다.

<!-- alj-install:start os=linux -->
```bash
git clone https://github.com/tony9402/algorithm-local-judge.git
cd algorithm-local-judge
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```
<!-- alj-install:end os=linux -->

프로그램은 `${XDG_DATA_HOME:-$HOME/.local/share}/algorithm-local-judge/runtime`에
설치되고, `judge`와 `problem-studio`는 `~/.local/bin`에 등록됩니다.

설치 스크립트가 운영체제와 Python 3.11 이상 실행 파일을 자동으로 찾습니다. 두 방식 모두
checkout 밖에 독립 실행 환경을 만들며 관리자 권한이나 전역 Python 환경을 변경하지 않습니다.
설치는 항상 전용 Python 가상환경에서만 진행되며, 기존 런타임이 Python 3.11 미만이거나
가상환경이 아니면 다른 설치 방법으로 넘어가지 않고 중단합니다. 새 터미널에서는 PATH 설정이
자동 적용됩니다.

## 문제 설치와 실행

이 저장소에는 채점 도구만 들어 있습니다. 문제 콘텐츠는 별도 저장소에서 관리되므로
checkout의 `problems/`에 포함되어 있지 않습니다.

```bash
judge problem install tony9402/algorithm-package
judge list
judge web
```

웹 브라우저에서 `http://127.0.0.1:8765`로 접속합니다. CLI로 바로 채점할 수도 있습니다.

```bash
judge run --problem <problem-id> --profile sample path/to/main.cpp
judge run --problem <problem-id> --profile sample path/to/main.py
```

문제를 만들거나 편집하려면 Problem Studio를 실행하고 `http://127.0.0.1:8775`로
접속합니다.

```bash
problem-studio web
```

설치 상태와 컴파일러 누락 여부는 `judge doctor --verbose`로 확인합니다.

## 문서

- [macOS 및 Linux 설치·운영 안내](INSTALL.md)
- [Judge 사용법](judge/README.md)
- [Problem Studio 사용법](problem_studio/README.md)

웹 서버는 개인 환경의 loopback 주소에서 사용하는 것을 전제로 합니다. 인증이나
멀티테넌트 격리를 제공하는 공유 서버로 공개하지 마세요.
