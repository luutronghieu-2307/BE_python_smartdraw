from fastapi import APIRouter

from app.api.v1.endpoints.classification import router as classification_router
from app.api.v1.endpoints.detection import router as detection_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.pipeline import router as pipeline_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(detection_router, prefix="/detect", tags=["detection"])
api_router.include_router(classification_router, prefix="/classify", tags=["classification"])
api_router.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])
