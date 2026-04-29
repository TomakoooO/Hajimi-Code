from time import time
from typing import Any
from uuid import uuid4


def ok(data: Any, message: str = "ok", request_id: str | None = None) -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": data,
        "request_id": request_id or f"req-{uuid4().hex[:12]}",
        "ts": int(time() * 1000),
    }


def err(code: int, message: str, request_id: str | None = None, status: int = 400) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": {"status": status},
        "request_id": request_id or f"req-{uuid4().hex[:12]}",
        "ts": int(time() * 1000),
    }
