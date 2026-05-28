class JudgeError(Exception):
    """User-facing error raised for recoverable judge failures."""

    pass


class SecurityPolicyError(JudgeError):
    """Raised when a request is blocked by an explicit security policy."""

    pass


class LimitExceededError(JudgeError):
    """Raised when an input exceeds a configured safety limit."""

    pass


class ConcurrencyLimitError(JudgeError):
    """Raised when a concurrent operation limit has been reached."""

    pass
