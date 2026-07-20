# macOS PKG 배포 계약

`scripts/build_macos_pkg.py`는 standalone 트리를
`/opt/algorithm-local-judge`에 설치하고 `judge`와 `problem-studio`를
`/usr/local/bin`에서 실행할 수 있도록 합니다.

Candidate 빌드는 의도적으로 서명하지 않으며 native 서명 증거를 `unconfigured`로
기록합니다. Stable 빌드는 Developer ID Application/Installer 인증서와 Apple
`notarytool` keychain profile이 모두 필요합니다. 빌더는 중첩 Mach-O를 안쪽부터 서명·검증한
뒤 installer 서명, 공증 승인, stapling, Gatekeeper 평가를 확인하고 `verified` 증거를
생성합니다. staging 전 archive 경로 순회와 링크도 거부합니다.

서명 identity나 공증 credential은 이 디렉터리에 커밋하지 않습니다.
