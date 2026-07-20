"""문제 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다."""

from __future__ import annotations

import argparse

from judge.core.errors import JudgeError
from judge.core.problem import discover_problem_ids, load_problem
from judge.core.problem_install_policy import PACK_INSTALL_POLICY
from judge.core.remote import install_problem_source


def print_installed_problem_source(result: dict) -> None:
    install_type = result.get("installType") or "pack"
    label = "source package" if install_type == "source" else "problem pack"
    print(f"Installed {label}: {result.get('label') or result.get('installedPath')}")
    if install_type == "source":
        print("Install type: source fallback")
    else:
        print("Install type: pack (.aljpack)")
    if repository := result.get("repository"):
        print(f"Repository: {repository}")
    if ref := result.get("ref"):
        print(f"Ref: {ref}")
    if commit_sha := result.get("commitSha"):
        print(f"Commit: {commit_sha}")
    if asset_name := result.get("assetName"):
        print(f"Asset: {asset_name}")
    if result.get("trustedRepository"):
        print("Trusted repository: verified")
    if result.get("checksumVerified"):
        print(f"Checksum: verified ({result.get('checksumSource')})")
    if result.get("signatureVerified"):
        print(f"Publisher signature: verified ({result.get('signatureSource')})")
    if problem_count := result.get("problemCount"):
        print(f"Problems: {problem_count}")
    if downloaded_path := result.get("downloadedPath"):
        print(f"Downloaded: {downloaded_path}")
    if install_type == "source":
        print(f"Policy: {PACK_INSTALL_POLICY}")
    if trust_warning := result.get("trustWarning"):
        print(trust_warning)
    print("Run `judge list` to see installed problems.")


def handle(args: argparse.Namespace) -> int:
    """problem CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    if args.problem_command == "install":
        result = install_problem_source(
            args.source,
            args.asset,
            args.ref,
            args.checksum,
            args.checksum_url,
            signature_url=getattr(args, "signature_url", None),
            require_pack=getattr(args, "require_pack", False),
        )
        print_installed_problem_source(result)
        return 0

    if args.problem_command == "list":
        problem_ids = discover_problem_ids()
        if not problem_ids:
            print("No problems installed.")
            return 0
        print("Problems:")
        for problem_id in problem_ids:
            _, _, metadata = load_problem(problem_id)
            print(f"  {problem_id}  {metadata.get('title', '')}")
        return 0

    raise JudgeError(f"unknown problem command: {args.problem_command}")
