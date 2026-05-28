"""streaming 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable, Iterator
from typing import Any

SSE_DONE = object()


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_operation(
    operation: Callable[[Callable[[str], None]], dict[str, Any]],
) -> Iterator[str]:
    events: queue.Queue[dict[str, Any] | object] = queue.Queue()

    def progress(message: str) -> None:
        events.put({"event": "log", "data": {"message": message}})

    def worker() -> None:
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
