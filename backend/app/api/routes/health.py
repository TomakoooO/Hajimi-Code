from fastapi import APIRouter

from app.core.response import ok

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return ok({"status": "up"}, request_id="local-health-check")
