"""streaming 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any

SSE_DONE = object()


def sse(event: str, data: dict[str, Any]) -> str:
    """sse 함수를 실행하고 결과를 반환합니다.
    
    Args:
        event (str): 발생한 이벤트입니다.
        data (dict[str, Any]): 처리할 데이터입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_operation(
    operation: Callable[[Callable[[str], None]], dict[str, Any]],
) -> Iterator[str]:
    """stream_operation 함수를 실행하고 결과를 반환합니다.
    
    Args:
        operation (Callable[[Callable[[str], None]], dict[str, Any]]): `operation` 값입니다.
    
    Returns:
        Iterator[str]: 처리 결과를 반환합니다.
    """
    events: queue.Queue[dict[str, Any] | object] = queue.Queue()

    def progress(message: str) -> None:
    """progress 함수를 실행하고 결과를 반환합니다.
    
    Args:
        message (str): 메시지입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
        events.put({"event": "log", "data": {"message": message}})

    def worker() -> None:
    """worker 함수를 실행하고 결과를 반환합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
        try:
            result = operation(progress)
            events.put({"event": "result", "data": result})
        except Exception as exc:  # noqa: BLE001 - errors are returned as SSE events.
            events.put({"event": "error", "data": {"message": str(exc)}})
        finally:
            events.put(SSE_DONE)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = events.get()
        if item is SSE_DONE:
            break
        if isinstance(item, dict):
            yield sse(str(item["event"]), item["data"])
