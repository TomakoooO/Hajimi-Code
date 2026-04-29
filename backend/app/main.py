from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.router import api_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.response import ok


# 增加全局中间件用于调试路由问题
class LogRequestsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        print(f"Incoming request: {request.method} {request.url.path}")
        response = await call_next(request)
        return response


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="🐱 ハジミ Code — Hajimi Code ✨",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        description="让编程像猫咪一样优雅 🐾 — 基于 FastAPI 的哈吉米代码编辑器后端",
    )
    app.add_middleware(LogRequestsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/")
    def index() -> dict:
        return ok(
            {
                "service": settings.app_name,
                "version": settings.app_version,
                "docs": "/docs",
                "health": f"{settings.api_prefix}/health",
            },
            request_id="local-index",
        )

    return app

# test5
app = create_app()
