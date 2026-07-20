# Windows 설치 관리자 소스

`scripts/build_windows_installer.py`는 검증된 `windows-amd64` standalone bundle을
WiX v4 source 파일로 변환합니다. MSI는 컴퓨터 전체(per-machine)에 설치되며 두 실행기를
추가하고 애플리케이션 `bin` 디렉터리만 `PATH`에 등록합니다. 사용자 데이터 디렉터리는
의도적으로 소유하지 않습니다.

Authenticode 서명과 WinGet 제출은 release pipeline 단계이며 로컬 generator가 수행하지
않습니다. 서명되지 않은 candidate MSI를 개인 컴퓨터 밖에 배포하지 마세요.
