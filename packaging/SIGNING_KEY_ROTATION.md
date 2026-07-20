# Signing key rotation and N-1 recovery

이 문서는 stable 배포에 쓰는 macOS Developer ID, Windows Authenticode, APT/RPM GPG 및
Sigstore identity의 교체·폐기 절차를 고정한다. 키나 토큰 값은 저장소, 로그, attestation에
기록하지 않는다.

## 공통 원칙

1. 침해가 의심되면 release workflow와 package repository publish 권한을 먼저 중지한다.
2. 영향받은 키·인증서·OIDC 권한을 발급자에서 폐기하고, 해당 fingerprint/identity를 denylist에
   추가한다.
3. 새 identity는 별도의 candidate release로 등록한다. 이전 identity를 조용히 덮어쓰지 않는다.
4. 새 candidate의 source commit, artifact hash, SBOM, provenance, native signing attestation을
   clean OS에서 검증한다.
5. N과 N-1을 새 identity로 다시 서명하되 version과 payload hash는 변경하지 않는다. payload가
   달라지면 새 patch version을 발행한다.
6. N 설치, N-1 rollback, N 재업그레이드, 제거 후 사용자 데이터 보존 smoke가 모두 통과한 뒤
   channel metadata와 README를 마지막에 승격한다.

## 플랫폼별 교체

- macOS: 새 Developer ID Installer certificate로 PKG를 서명하고 notarization·stapling 후
  `pkgutil --check-signature`와 `spctl` 결과를 attestation에 남긴다. 폐기된 Team ID는 stable
  manifest validator allowlist에서 제거한다.
- Windows: 새 code-signing certificate와 신뢰 가능한 timestamp를 사용한다. MSI의 UpgradeCode는
  바꾸지 않는다. `Get-AuthenticodeSignature`의 signer와 유효 상태를 기록하고 WinGet manifest의
  installer SHA를 다시 고정한다.
- APT/RPM: repository metadata와 package signing key를 분리한다. 새 public key를 N-1 repository
  bootstrap package에 먼저 포함한 뒤 dual-sign 전환 기간을 거친다. 폐기 키는 bootstrap과
  repository metadata에서 제거하고 fingerprint를 attestation에 기록한다.
- Sigstore: GitHub OIDC subject와 issuer를 repository/tag workflow에 고정한다. workflow identity가
  바뀌면 기존 identity와 새 identity를 명시적으로 검증하는 한 번의 전환 release를 사용하고,
  이후 이전 subject를 제거한다.

## 실패 시 복구

- 새 identity 검증이 하나라도 실패하면 stable pointer, package index, README 설치 명령을 변경하지
  않는다.
- 이미 승격한 뒤 문제가 발견되면 마지막 검증된 N-1 channel metadata를 복원하고 availability
  smoke를 다시 실행한다. 사용자 pack, 제출 기록, Studio workspace는 package rollback 대상이 아니다.
- N-1 artifact나 서명 증거를 재현할 수 없으면 rollback을 제공하는 척하지 않고 해당 채널을
  `unpublished`로 내린다.
- incident 종료 후 폐기 시각, 영향 version, 새 fingerprint/identity, N/N-1 smoke hash를 공개
  incident record에 남긴다. secret이나 개인 인증서 내용은 포함하지 않는다.

## 승격 체크리스트

- 폐기된 identity가 validator와 배포 자격증명에서 제거됨
- 새 identity의 candidate manifest·native attestation 검증 완료
- N/N-1 install·upgrade·rollback·uninstall 및 데이터 보존 완료
- 공개 package index와 GitHub release 재다운로드 hash 일치
- 네 설치 채널의 README 명령과 clean-OS 명령이 일치

