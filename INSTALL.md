# 개인 설치 및 운영 안내

이 문서는 GitHub에서 소스를 내려받아 현재 사용자만 사용하는 Judge와 Problem Studio를
설치하는 가장 짧은 경로를 설명합니다. 설치 스크립트는 저장소 안에 `.venv`를 만들고,
`uv`가 있으면 `uv.lock`을 고정 사용하며, 없으면 표준 Python 가상환경과 `pip`를 사용합니다.
`sudo`, 관리자 권한, 전역 PATH 변경은 요구하지 않습니다.

## 지원 범위와 준비물

- macOS, Linux, Windows PowerShell에서 개인 로컬 실행을 지원합니다.
- Git과 Python 3.11 이상이 필요합니다. 설치 스크립트가 버전을 먼저 확인하고 부족하면
  OS별 설치 안내와 함께 중단합니다.
- `uv`는 선택 사항입니다. 설치되어 있으면 잠금 파일을 사용하고, 없어도 `pip` 경로로
  설치할 수 있습니다.
- C++/Java/PyPy 제출을 실행하려면 해당 컴파일러·런타임이 추가로 필요합니다. 설치
  스크립트는 이를 몰래 설치하지 않고 `judge doctor`에 누락 항목과 복구 힌트를 표시합니다.
- Docker는 선택 사항이며, 비신뢰 제출을 격리할 때만 필요합니다. 개인 로컬 모드와 공유
  서버용 엔터프라이즈 모드는 같은 보안 경계가 아닙니다.

`uv`를 사용할 수 없는 개인 환경의 `pip` fallback은 `pyproject.toml`의 허용 범위 안에서
패키지를 해결하므로, 장기간 재현이 필요한 팀은 `uv.lock`을 사용하는 설치나 사내 wheel
mirror를 선택하세요. 운영 배포에는 이 소스 설치 대신 서명된 native artifact가 필요합니다.

## macOS / Linux: 세 명령

```bash
git clone --depth 1 https://github.com/tony9402/algorithm-local-judge.git
cd algorithm-local-judge
./install.sh
```

설치가 끝나면 다음 실행 파일이 저장소 안에 생깁니다.

```bash
./.venv/bin/judge web
./.venv/bin/problem-studio web
./.venv/bin/judge doctor --verbose
```

스크립트가 실행 권한을 잃은 checkout에서는 `bash install.sh`로 실행할 수 있습니다.
네트워크 없는 환경은 미리 준비한 `uv` cache 또는 Python wheel이 있어야 하며, 외부에서
도구를 내려받는 것으로 가장하지 않습니다.

## Windows PowerShell: 세 명령

```powershell
git clone --depth 1 https://github.com/tony9402/algorithm-local-judge.git
Set-Location algorithm-local-judge
.\install.ps1
```

설치 후:

```powershell
& ".\.venv\Scripts\judge.exe" web
& ".\.venv\Scripts\problem-studio.exe" web
& ".\.venv\Scripts\judge.exe" doctor --verbose
```

PowerShell 실행 정책이 스크립트를 막으면 현재 사용자 범위에서만 일시적으로 허용합니다.
조직 정책을 우회하지 말고 관리자에게 서명된 스크립트 정책을 확인하세요.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

## 설치 점검과 첫 문제 팩

`install.sh`와 `install.ps1`은 설치 직후 `judge doctor --verbose`를 실행합니다. 상태가
`WARN`이어도 설치 자체는 끝날 수 있지만, 제출 언어별 실행 파일이 `missing`이면 해당
언어를 채점하기 전에 준비해야 합니다. 공식 문제 팩은 다음처럼 명시적으로 설치합니다.

```bash
./.venv/bin/judge problem install tony9402/algorithm-package
./.venv/bin/judge list
```

공식 release pack은 체크섬과 Sigstore 게시자 검증을 거쳐야 하며, 임의의 저장소·압축 파일을
설치하지 마세요. 설치 팩이 없을 때 자동으로 임의의 저장소를 선택하지 않는 것이 기본입니다.

## 업데이트, 롤백, 제거

### 업데이트

소스 checkout 방식은 Git commit을 기준으로 업데이트합니다. 먼저 데이터와 현재 변경을
보존한 뒤 새 commit을 설치하세요.

```bash
git status --short
git pull --ff-only
./install.sh
```

`git pull --ff-only`가 거부되면 충돌 해결이나 강제 checkout을 자동으로 수행하지 않습니다.
현재 branch와 로컬 변경을 검토한 후 별도 branch/worktree에서 업데이트하세요.

### 롤백

문제 발생 시 저장소를 이전 tag 또는 commit으로 되돌린 별도 worktree를 만들고 같은 설치
스크립트를 다시 실행합니다. Judge 문제 팩과 제출 기록은 저장소 밖의 사용자 데이터에 있어
checkout 변경만으로 삭제되지 않습니다. Problem Studio workspace 파일은 사용자가 선택한
저장소에 남으므로 rollback 전 Git 상태를 먼저 확인하세요.

```bash
git worktree add ../algorithm-local-judge-rollback <이전-태그-또는-커밋>
cd ../algorithm-local-judge-rollback
../algorithm-local-judge/install.sh --skip-checks
```

Windows에서는 `git worktree add ..\algorithm-local-judge-rollback <커밋>` 후
`..\algorithm-local-judge\install.ps1 -SkipChecks`를 사용합니다. 이전 버전과 현재
버전이 같은 `$ALJ_DATA_HOME`을 공유하므로, 데이터 형식 변경이 있는 release는 release
notes의 migration 지시를 먼저 확인하세요.

### 제거와 데이터 보존

소스 설치 제거는 checkout과 `.venv`만 삭제하면 됩니다. 문제 팩·캐시·제출 기록은 기본적으로
보존됩니다. 먼저 `judge doctor --verbose`에서 데이터 경로를 확인하고, 필요한 경우 백업한
뒤에 명시적으로 지우세요.

```bash
./.venv/bin/judge doctor --verbose
rm -rf .venv
```

`$ALJ_DATA_HOME` 아래 `problem-packs`, `problem-sources`, `jobs`, 제출 소스·결과를 지우는
작업은 복구할 수 없습니다. 전체 캐시 삭제 전에는 `judge cache clear --all --dry-run`을
실행하고, 기록을 삭제할 때는 웹의 전체 제출 삭제 확인 절차를 사용하세요. Windows는
`.venv` 폴더를 삭제하고 `%LOCALAPPDATA%\algorithm-local-judge`를 백업/삭제 대상으로
선택합니다.

## 언어 도구체인 준비

설치 스크립트는 컴파일러를 관리자 권한으로 설치하지 않습니다. `doctor` 출력의 `install`
힌트를 따라 OS 패키지 관리자가 제공하는 공식 패키지를 설치하세요.

| 언어 | 확인 명령 | 후보 실행 파일 |
| --- | --- | --- |
| C++ | `g++ --version` | `g++` |
| Java | `javac -version`, `java -version` | `javac`, `java` |
| Python | `python3 --version` | `python3`, `python` |
| PyPy | `pypy3 --version` | `pypy3`, `pypy` |

실행 파일 위치를 별도로 관리해야 하면 `ALJ_CXX`, `ALJ_JAVAC`, `ALJ_JAVA`, `ALJ_PYTHON`,
`ALJ_PYPY` 환경 변수로 명시합니다. 설치 후 `judge doctor --json`을 저장하면 지원 요청에
필요한 상태를 재현할 수 있습니다. 소스·토큰·비밀 값이 포함된 로그를 외부에 공유하지 마세요.

## 개인 모드와 엔터프라이즈 모드의 경계

기본 `judge web`과 `problem-studio web`은 `127.0.0.1`에만 바인딩하는 개인용 도구입니다.
외부 주소에 공개하면 인증·RBAC·멀티테넌트 worker 격리·감사 로그·소스 보존 정책이 자동으로
생기지 않습니다. 회사 서버나 수업/시험 환경에 공유하지 마세요.

엔터프라이즈 배포는 다음을 별도로 구현·검증해야 합니다.

1. SSO/인증, 역할별 문제·제출·Git 권한, 관리자 감사 로그
2. 제출 실행 worker와 web control plane의 프로세스/컨테이너·네트워크 격리
3. 제출 소스 암호화·OS별 ACL·보존 기간·삭제 복구 정책
4. 프로세스 간 job lock, 충돌 해결, 백업·복구·지원 번들
5. macOS/Windows/Linux 서명·체크섬·clean-OS install/upgrade/rollback smoke

현재 공개 저장소의 native 패키지 채널은 이 증거가 모두 게시되기 전까지 미공개 상태입니다.
검증되지 않은 `brew`, `apt`, `dnf`, `winget` 명령이나 raw branch 설치 명령을 배포 문서에
추가하지 마세요. 채널 상태·stable gate의 자세한 계약은
`packaging/install-channels.json`과 `scripts/verify_install_docs.py`를 확인합니다.

## 설치 문제 해결

- `Python 3.11 이상이 필요합니다`: 공식 Python 설치 후 새 터미널에서 `python3 --version`
  (Windows는 `py -3 --version`)을 확인하고 설치 스크립트를 다시 실행합니다.
- `pip` 다운로드 실패: 네트워크/사내 mirror를 확인하고, 준비된 wheel cache에서 설치하거나
  `uv sync --frozen`을 사용합니다. 임의의 패키지 URL을 스크립트에 넣지 마세요.
- 컴파일러 `missing`: `judge doctor --verbose`의 OS별 힌트를 실행한 뒤 다시 doctor를
  호출합니다. 설치 스크립트는 성공한 것처럼 숨기지 않습니다.
- 문제 목록이 비어 있음: `judge problem install tony9402/algorithm-package`를 실행하고
  서명·체크섬 오류가 있으면 중단 원인을 먼저 확인합니다.
- 웹이 열리지 않음: `./.venv/bin/judge web --no-open` 또는 Windows의 `judge.exe web
  --no-open`으로 실행한 뒤 `http://127.0.0.1:8765`를 직접 엽니다.

## 검증 명령(개발·CI)

```bash
bash -n install.sh
python3 -m scripts.verify_install_docs
python3 -m unittest tests.test_local_installer tests.install.test_install_docs
```

stable 검증은 모든 native 채널의 서명·clean-OS 증거가 게시되기 전까지 의도적으로 실패합니다.
이는 사용자에게 가짜 다운로드 경로를 보여주지 않기 위한 안전장치입니다.
