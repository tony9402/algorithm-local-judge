"""Problem Studio 작업 공간의 Git 저장소 검증, 상태 조회, 커밋/푸시 정책을 담당합니다.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from judge.core.errors import JudgeError

ALLOWED_COMMIT_PREFIXES = ("problems/",)
ALLOWED_COMMIT_FILES = {"testlib.h"}
BLOCKED_COMMIT_PREFIXES = (".judge-cache/", "build/", "dist/", ".git/")
BLOCKED_COMMIT_FILES = {".env", ".env.local", "id_rsa", "id_ed25519"}
DEFAULT_PROBLEM_REPOSITORY = "tony9402/algorithm-package"
PROBLEM_REPOSITORY_ENV = "ALJ_PROBLEM_STUDIO_REPOSITORY"
TOOL_REPOSITORY_NAMES = {
    "algorithm-local-judge",
    "algorithm-problem-judger",
    "problem-studio",
}
GIT_URL_SCHEME_RE = re.compile(r"^(https|ssh)://", re.IGNORECASE)
GIT_SCP_RE = re.compile(r"^[A-Za-z0-9_.-]+@[^:]+:.+")
GITHUB_SCP_RE = re.compile(r"^(?:git@)?github\.com:([^/]+)/(.+)$", re.IGNORECASE)
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GIT_OUTPUT_LIMIT = 4000


def run_git(
    workspace: Path,
    args: list[str],
    *,
    timeout_seconds: int = 30,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """지정한 작업 공간에서 Git 명령을 실행하고 실패한 명령의 출력을 제한해 JudgeError로 변환합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        args (list[str]): git 실행 파일 뒤에 그대로 전달할 하위 명령과 옵션 목록입니다.
        timeout_seconds (int): Git, 서버, 장시간 작업에 허용할 제한 시간입니다. 단위는 초입니다.
        check (bool): Git 명령 실패를 예외로 바꿀지 결정하는 플래그입니다.

    Returns:
        subprocess.CompletedProcess[str]: Git 명령의 종료 코드, 표준 출력, 표준 오류를 담은 실행 결과입니다.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise JudgeError("git executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise JudgeError(f"git command timed out: git {' '.join(args)}") from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if len(detail) > GIT_OUTPUT_LIMIT:
            detail = "...truncated...\n" + detail[-GIT_OUTPUT_LIMIT:]
        raise JudgeError(detail or f"git command failed: git {' '.join(args)}")
    return result


def is_git_repository(workspace: Path) -> bool:
    """작업 공간이 Git working tree인지 rev-parse 결과로 확인합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.

    Returns:
        bool: Git 저장소 조건을 만족하면 True, 아니면 False입니다.
    """
    if not workspace.exists():
        return False
    result = run_git(workspace, ["rev-parse", "--is-inside-work-tree"], check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_git_repository(workspace: Path) -> None:
    """작업 공간이 Git 저장소가 아니면 이후 Git 작업을 막는 JudgeError를 발생시킵니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
    """
    if not is_git_repository(workspace):
        raise JudgeError("workspace is not a Git repository")


def redact_remote_url(url: str) -> str:
    """원격 URL에서 사용자 정보와 인증 정보를 제거해 로그에 안전한 형태로 만듭니다.

    Args:
        url (str): 브라우저 또는 Git 명령에 전달할 URL입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 redact 원격 URL 문자열입니다.
    """
    if "://" not in url:
        return url
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def normalize_github_repository(owner: str, repo: str) -> str:
    """GitHub owner/name 값을 검증하고 .git 접미사를 제거한 표준 저장소 이름을 만듭니다.

    Args:
        owner (str): GitHub 저장소을 계산하거나 검증할 때 필요한 소유자 입력입니다.
        repo (str): 작업 공간에서 선택하거나 조작할 저장소 이름 또는 경로입니다.

    Returns:
        str: 정책 검사를 통과한 표준 GitHub 저장소 문자열입니다.
    """
    repo = repo.removesuffix(".git")
    candidate = f"{owner}/{repo}"
    if not GITHUB_REPOSITORY_RE.fullmatch(candidate):
        raise JudgeError("GitHub repository must look like owner/name")
    return candidate


def github_repository_from_remote(source: str | None) -> str | None:
    """GitHub URL, SCP 형식, owner/name 입력에서 GitHub 저장소 이름을 추출합니다.

        Args:
            source (str | None): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
    """
    value = (source or "").strip()
    if not value:
        return None
    if GITHUB_REPOSITORY_RE.fullmatch(value):
        owner, repo = value.split("/", 1)
        return normalize_github_repository(owner, repo)

    scp_match = GITHUB_SCP_RE.fullmatch(value)
    if scp_match:
        return normalize_github_repository(scp_match.group(1), scp_match.group(2))

    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme in {"http", "https", "ssh"} and host in {"github.com", "www.github.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return normalize_github_repository(parts[0], parts[1])
    return None


def expected_problem_repository() -> str:
    """환경 변수 또는 기본값에서 Problem Studio가 사용할 공식 문제 저장소 이름을 결정합니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 기대 문제 저장소 문자열입니다.
    """
    configured = os.environ.get(PROBLEM_REPOSITORY_ENV) or DEFAULT_PROBLEM_REPOSITORY
    parsed = github_repository_from_remote(configured)
    if parsed is None:
        raise JudgeError(f"{PROBLEM_REPOSITORY_ENV} must look like owner/name or a GitHub URL")
    return parsed


def repository_name(repository: str | None) -> str | None:
    """원격 저장소 문자열에서 작업 공간 디렉터리 이름으로 사용할 저장소 이름을 추출합니다.

        Args:
            repository (str | None): GitHub owner/name 또는 URL에서 정규화할 저장소 식별자입니다.
    """
    if not repository:
        return None
    return repository.split("/", 1)[1].removesuffix(".git").lower()


def repository_safety(remote: str | None) -> dict[str, Any]:
    expected = expected_problem_repository()
    expected_name = repository_name(expected)
    detected = github_repository_from_remote(remote)
    detected_name = repository_name(detected)
    problem_remote = bool(detected_name and detected_name == expected_name)
    tool_remote = bool(detected_name and detected_name in TOOL_REPOSITORY_NAMES)
    warning = None
    if tool_remote:
        warning = {
            "kind": "toolRepository",
            "title": "문제 저장소가 아닙니다",
            "message": (
                f"현재 원격 저장소는 {detected} 입니다. 문제 파일은 "
                f"{expected} 또는 그 fork에 올려야 하므로 Git 동기화 작업을 막았습니다."
            ),
        }
    elif detected and not problem_remote:
        warning = {
            "kind": "unexpectedRepository",
            "title": "원격 저장소 확인 필요",
            "message": (
                f"현재 원격 저장소는 {detected} 입니다. 문제 파일은 "
                f"{expected} 또는 그 fork에 올리는 것을 권장합니다."
            ),
        }
    return {
        "expectedProblemRepository": expected,
        "detectedRepository": detected,
        "problemRepositoryRemote": problem_remote,
        "toolRepositoryRemote": tool_remote,
        "repositoryWarning": warning,
    }


def ensure_problem_repository_remote(workspace: Path) -> None:
    """문제 저장소 원격 조건을 확인하고 위반 시 호출자가 중단할 수 있는 예외를 발생시킵니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
    """
    safety = repository_safety(remote_url(workspace))
    if safety["toolRepositoryRemote"]:
        warning = safety.get("repositoryWarning") or {}
        raise JudgeError(
            warning.get("message") or "Problem Studio is connected to the wrong repository"
        )


def git_stdout(workspace: Path, args: list[str], *, check: bool = True) -> str:
    return run_git(workspace, args, check=check).stdout.rstrip("\n")


def current_branch(workspace: Path) -> str | None:
    """현재 Git 브랜치 이름을 조회하고 detached HEAD 상태이면 None을 반환합니다.

        Args:
            workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
    """
    result = run_git(workspace, ["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    if result.returncode != 0:
        branch_result = run_git(workspace, ["symbolic-ref", "--short", "HEAD"], check=False)
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    else:
        branch = result.stdout.strip()
    return None if branch == "HEAD" else branch


def current_head(workspace: Path) -> str | None:
    """현재 HEAD 커밋 해시를 조회해 작업 공간 상태 응답에 포함할 값으로 만듭니다.

        Args:
            workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
    """
    result = run_git(workspace, ["rev-parse", "--short", "HEAD"], check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def upstream_branch(workspace: Path) -> str | None:
    """현재 브랜치가 추적하는 upstream 브랜치 이름을 조회합니다.

        Args:
            workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
    """
    result = run_git(
        workspace,
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def remote_url(workspace: Path, remote: str = "origin") -> str | None:
    """지정한 Git remote의 URL을 조회하고 로그에 안전하게 인증 정보를 제거합니다.

        Args:
            workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
            remote (str): 조회할 Git 원격 저장소 이름입니다.
    """
    result = run_git(workspace, ["remote", "get-url", remote], check=False)
    if result.returncode != 0:
        return None
    return redact_remote_url(result.stdout.strip())


def ahead_behind(workspace: Path, upstream: str | None) -> tuple[int, int]:
    if not upstream:
        return 0, 0
    result = run_git(workspace, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def parse_status_paths(output: str) -> list[dict[str, str]]:
    """상태 경로 원본 입력을 내부 로직이 사용할 구조로 해석합니다.

    Args:
        output (str): 상태 경로을 계산하거나 검증할 때 필요한 출력 입력입니다.

    Returns:
        list[dict[str, str]]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 상태 경로 데이터입니다.
    """
    files = []
    for line in output.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append({"status": status.strip() or "modified", "path": path})
    return files


def git_status(workspace: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    if not is_git_repository(workspace):
        return {
            "isRepository": False,
            "workspace": str(workspace),
            "branch": None,
            "head": None,
            "upstream": None,
            "remote": None,
            "ahead": 0,
            "behind": 0,
            "protectedBranch": False,
            "dirty": False,
            "files": [],
            **repository_safety(None),
        }
    branch = current_branch(workspace)
    upstream = upstream_branch(workspace)
    ahead, behind = ahead_behind(workspace, upstream)
    files = parse_status_paths(git_stdout(workspace, ["status", "--porcelain=v1"]))
    remote = remote_url(workspace)
    return {
        "isRepository": True,
        "workspace": str(workspace),
        "branch": branch,
        "head": current_head(workspace),
        "upstream": upstream,
        "remote": remote,
        "ahead": ahead,
        "behind": behind,
        "protectedBranch": False,
        "dirty": bool(files),
        "files": files,
        **repository_safety(remote),
    }


def normalize_git_url(url: str) -> str:
    """Git URL 입력을 비교와 저장에 쓰기 쉬운 표준 형식으로 정규화합니다.

    Args:
        url (str): 브라우저 또는 Git 명령에 전달할 URL입니다.

    Returns:
        str: 정책 검사를 통과한 표준 Git URL 문자열입니다.
    """
    value = url.strip()
    if not value:
        raise JudgeError("git repository URL is required")
    if GITHUB_REPOSITORY_RE.fullmatch(value):
        return f"https://github.com/{value}.git"
    if GIT_URL_SCHEME_RE.match(value) or GIT_SCP_RE.match(value):
        return value
    local = Path(value).expanduser()
    if local.exists():
        return str(local.resolve())
    raise JudgeError("git URL must be https, ssh, owner/name, or an existing local path")


def clone_repository(url: str, target: Path, branch: str | None = None) -> dict[str, Any]:
    """clone 저장소 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        url (str): 브라우저 또는 Git 명령에 전달할 URL입니다.
        target (Path): 파일을 복사하거나 산출물을 배치할 대상 경로입니다.
        branch (str | None): clone 저장소을 계산하거나 검증할 때 필요한 브랜치 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 clone 저장소 데이터입니다.
    """
    clone_url = normalize_git_url(url)
    target = target.expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise JudgeError(f"clone target is not empty: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    command = ["clone"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([clone_url, str(target)])
    run_git(target.parent, command, timeout_seconds=120)
    return git_status(target)


def normalized_commit_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip().lstrip("./")
    parts = [part for part in normalized.split("/") if part]
    if not parts or any(part == ".." for part in parts):
        raise JudgeError(f"invalid commit path: {path}")
    return "/".join(parts)


def allowed_commit_path(path: str) -> bool:
    normalized = normalized_commit_path(path)
    lowered = normalized.lower()
    if normalized in ALLOWED_COMMIT_FILES:
        return True
    if any(lowered == name or lowered.endswith("/" + name) for name in BLOCKED_COMMIT_FILES):
        return False
    if any(normalized.startswith(prefix) for prefix in BLOCKED_COMMIT_PREFIXES):
        return False
    return any(normalized.startswith(prefix) for prefix in ALLOWED_COMMIT_PREFIXES)


def dirty_paths(workspace: Path) -> list[str]:
    output = git_stdout(workspace, ["status", "--porcelain=v1"])
    return [item["path"] for item in parse_status_paths(output)]


def staged_paths(workspace: Path) -> list[str]:
    output = git_stdout(workspace, ["diff", "--cached", "--name-only"])
    return [line for line in output.splitlines() if line]


def commit_changes(
    workspace: Path,
    message: str,
    files: list[str] | None = None,
) -> dict[str, Any]:
    ensure_git_repository(workspace)
    ensure_problem_repository_remote(workspace)
    message = message.strip()
    if not message:
        raise JudgeError("commit message is required")
    existing_staged = staged_paths(workspace)
    if existing_staged:
        raise JudgeError(
            "there are already staged files; unstage them before using Problem Studio"
        )
    selected = files or dirty_paths(workspace)
    allowed = [normalized_commit_path(path) for path in selected if allowed_commit_path(path)]
    rejected = sorted({normalized_commit_path(path) for path in selected} - set(allowed))
    if rejected:
        raise JudgeError("refusing to stage unsupported path(s): " + ", ".join(rejected))
    if not allowed:
        raise JudgeError("no allowed problem files to commit")
    run_git(workspace, ["add", "--", *allowed])
    if not staged_paths(workspace):
        raise JudgeError("no changes staged for commit")
    run_git(workspace, ["commit", "-m", message], timeout_seconds=60)
    return git_status(workspace)


def fetch_repository(workspace: Path) -> dict[str, Any]:
    ensure_git_repository(workspace)
    ensure_problem_repository_remote(workspace)
    run_git(workspace, ["fetch", "--prune"], timeout_seconds=120)
    return git_status(workspace)


def pull_repository(workspace: Path) -> dict[str, Any]:
    ensure_git_repository(workspace)
    ensure_problem_repository_remote(workspace)
    run_git(workspace, ["pull", "--ff-only"], timeout_seconds=120)
    return git_status(workspace)


def push_repository(workspace: Path) -> dict[str, Any]:
    ensure_git_repository(workspace)
    ensure_problem_repository_remote(workspace)
    status = git_status(workspace)
    branch = status.get("branch")
    if not branch:
        raise JudgeError("cannot push detached HEAD")
    if int(status.get("behind") or 0) > 0:
        raise JudgeError("branch is behind upstream; pull before pushing")
    if status.get("upstream"):
        run_git(workspace, ["push"], timeout_seconds=120)
    else:
        run_git(workspace, ["push", "-u", "origin", str(branch)], timeout_seconds=120)
    return git_status(workspace)
