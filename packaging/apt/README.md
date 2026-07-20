# Debian APT 배포 계약

`scripts/build_apt_repository.py`는 애플리케이션 DEB, `Packages`, `Packages.gz`,
`Release`가 포함된 저장소 archive를 만듭니다. Candidate 산출물은 의도적으로 서명하지
않으므로 stable release gate를 통과할 수 없습니다.

Stable 산출물에는 설정된 OpenPGP 서명 키와 실제 HTTPS 채널이 추가로 필요합니다.
`InRelease`와 `Release.gpg`를 만들고 검증한 뒤, 공개 키만 포함하는
`algorithm-local-judge-archive-keyring` bootstrap DEB와 `Signed-By` pinning이 있는
Deb822 source를 별도로 만듭니다.

개인 키·공개 키·저장소 도메인은 배포 환경 입력이며 이 디렉터리에 커밋하지 않습니다.
