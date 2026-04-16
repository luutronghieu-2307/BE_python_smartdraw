from fastapi import APIRouter

from app.api.v1.endpoints.classification import router as classification_router
from app.api.v1.endpoints.detection import router as detection_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.light import router as light_router
from app.api.v1.endpoints.pipeline import router as pipeline_router
from app.api.v1.endpoints.drawer import router as drawer_router
from app.api.v1.endpoints.fcm import router as fcm_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(detection_router, prefix="/detect", tags=["detection"])
api_router.include_router(classification_router, prefix="/classify", tags=["classification"])
api_router.include_router(light_router, prefix="/light", tags=["light"])
api_router.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])
api_router.include_router(drawer_router, prefix="/drawer", tags=["drawer"])
api_router.include_router(fcm_router, prefix="/fcm", tags=["fcm"])
