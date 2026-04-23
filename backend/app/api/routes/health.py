from time import time

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {
        "code": 0,
        "message": "ok",
        "data": {"status": "up"},
        "request_id": "local-health-check",
        "ts": int(time() * 1000),
    }
