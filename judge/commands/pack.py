from __future__ import annotations

import argparse
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.pack import build_pack, install_pack, installed_packs, remove_pack, verify_pack
from judge.core.paths import current_platform_id, rel


def handle(args: argparse.Namespace) -> int:
    """Handle `judge pack ...` subcommands."""
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
    raise JudgeError(f"unknown pack command: {args.pack_command}")
