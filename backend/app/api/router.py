from fastapi import APIRouter

from app.api.routes.chat import router as chat_router
from app.api.routes.code import router as code_router
from app.api.routes.health import router as health_router
from app.api.routes.ide import router as ide_router
from app.api.routes.review import router as review_router
from app.api.routes.timeline import router as timeline_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(code_router, tags=["code"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(timeline_router, tags=["timeline"])
api_router.include_router(ide_router, tags=["ide"])
api_router.include_router(review_router, tags=["review"])
