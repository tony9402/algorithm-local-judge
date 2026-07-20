"""Judge Web 제출 간격 제한을 관리합니다."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    accepted: bool
    retry_after_seconds: int = 0


class SubmissionRateLimiter:
    def __init__(self, cooldown_seconds: int = 5) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._last_submission: dict[str, float] = {}

    def check_and_record(self, problem_id: str) -> RateLimitDecision:
        now = time.monotonic()
        with self._lock:
            previous = self._last_submission.get(problem_id)
            if previous is not None:
                elapsed = now - previous
                if elapsed < self.cooldown_seconds:
                    remaining = max(1, int(self.cooldown_seconds - elapsed + 0.999))
                    return RateLimitDecision(False, remaining)
            self._last_submission[problem_id] = now
        return RateLimitDecision(True, 0)
