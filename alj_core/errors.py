"""errors 도메인 로직과 파일시스템 변경 정책을 담당합니다."""


class JudgeError(Exception):
    """저지 오류 상황을 상위 계층에 명확히 전달하기 위한 예외입니다."""

    pass


class SecurityPolicyError(JudgeError):
    """보안 정책 오류 상황을 상위 계층에 명확히 전달하기 위한 예외입니다."""

    pass


class LimitExceededError(JudgeError):
    """제한 exceeded 오류 상황을 상위 계층에 명확히 전달하기 위한 예외입니다."""

    pass


class ConcurrencyLimitError(JudgeError):
    """concurrency 제한 오류 상황을 상위 계층에 명확히 전달하기 위한 예외입니다."""

    pass


class SubmissionCompileError(JudgeError):
    """A user submission failed compilation after its run context was created."""

    def __init__(self, message: str, *, run_id: str, result: dict) -> None:
        super().__init__(message)
        self.run_id = run_id
        self.result = dict(result)
