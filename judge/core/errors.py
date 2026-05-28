"""errors 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
class JudgeError(Exception):
    """JudgeError 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    pass


class SecurityPolicyError(JudgeError):
    """SecurityPolicyError 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    pass


class LimitExceededError(JudgeError):
    """LimitExceededError 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    pass


class ConcurrencyLimitError(JudgeError):
    """ConcurrencyLimitError 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    pass
