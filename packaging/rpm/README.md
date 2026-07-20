# Fedora RPM 패키지 소스

`scripts/build_rpm.py`는 검증된 `linux-amd64` standalone archive를 입력으로 받아
서명하지 않은 로컬 artifact 두 개를 만듭니다.

- `algorithm-local-judge`: Judge와 Problem Studio를 `/opt` 아래에 설치하고 두 실행기를
  `/usr/bin`에 노출합니다.
- `alj-release`: `dnf config-manager` 없이 서명된 DNF 저장소 설정을 설치합니다.

패키지는 의도적으로 사용자별 데이터의 소유권을 갖거나 데이터를 삭제하지 않습니다.
GPG 서명과 DNF 저장소 metadata 공개는 release pipeline의 책임이며 이 로컬 빌더가
수행하지 않습니다.
