from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")

app.include_router(api_router, prefix="/api/v1")

media_dir = Path("media")
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}
