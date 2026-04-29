import asyncio
from time import time

from app.core.config import settings


async def call_llm_with_retry(prompt: str, model: str | None = None) -> dict:
    last_error: Exception | None = None
    for _ in range(settings.llm_retry_times + 1):
        try:
            return await asyncio.wait_for(_call_placeholder(prompt, model), timeout=settings.llm_timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    return {
        "text": "【占位】Agent 能力尚未开发，当前返回固定语句。",
        "model": model or "placeholder-model",
        "latency_ms": -1,
        "error": str(last_error) if last_error else "unknown",
    }


async def _call_placeholder(prompt: str, model: str | None) -> dict:
    started = int(time() * 1000)
    await asyncio.sleep(0.05)
    return {
        "text": f"【占位】收到请求：{prompt[:60]}",
        "model": model or "placeholder-model",
        "latency_ms": int(time() * 1000) - started,
    }
