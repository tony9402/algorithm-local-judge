"""pack 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.pack import build_pack, install_pack, installed_packs, remove_pack, verify_pack
from judge.core.paths import current_platform_id, rel
from judge.core.remote_trust import (
    add_user_trusted_repository,
    default_trusted_repositories,
    load_user_trusted_repositories,
    remove_user_trusted_repository,
)


def handle(args: argparse.Namespace) -> int:
    """handle 함수를 실행하고 결과를 반환합니다.
    
    Args:
        args (argparse.Namespace): `args` 값입니다.
    
    Returns:
        int: 처리 결과를 반환합니다.
    """
    if args.pack_command == "build":
        result = build_pack(
            Path(args.problem_path),
            args.pack_id,
            args.platform or current_platform_id(),
            Path(args.out),
            args.verify_profile,
        )
        print(
            "Verified solution expectations: "
            f"{len(result.solution_checks)} solution(s) on profile {args.verify_profile}"
        )
        print(f"Built pack: {rel(result.archive_path)}")
        return 0
    if args.pack_command == "verify":
        pack = verify_pack(Path(args.archive))
        print(
            f"Verified pack: {pack['packId']} "
            f"{pack.get('version', '')} "
            f"({', '.join(pack.get('supportedPlatforms', []))})"
        )
        return 0
    if args.pack_command == "install":
        target = install_pack(Path(args.archive))
        print(f"Installed pack: {rel(target)}")
        return 0
    if args.pack_command == "list":
        packs = installed_packs()
        if not packs:
            print("No problem packs installed.")
            return 0
        print("Problem packs:")
        for pack in packs:
            platforms = ", ".join(pack.get("supportedPlatforms", []))
            problems = ", ".join(pack.get("problems", []))
            print(
                f"  {pack['packId']} {pack.get('version', '')} [{platforms}] problems: {problems}"
            )
        return 0
    if args.pack_command == "remove":
        removed = remove_pack(args.pack_id)
        print(f"Removed pack: {rel(removed)}")
        return 0
    if args.pack_command == "trust":
        if args.trust_command == "list":
            print("Trusted repositories:")
            for repository in default_trusted_repositories():
                print(f"  {repository} (default)")
            for repository in load_user_trusted_repositories():
                print(f"  {repository} (user)")
            return 0
        if args.trust_command == "add":
            repository = add_user_trusted_repository(args.repository)
            print(f"Trusted repository added: {repository}")
            return 0
        if args.trust_command == "remove":
            repository = remove_user_trusted_repository(args.repository)
            print(f"Trusted repository removed: {repository}")
            return 0
        raise JudgeError(f"unknown pack trust command: {args.trust_command}")
    raise JudgeError(f"unknown pack command: {args.pack_command}")
