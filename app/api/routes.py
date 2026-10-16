from fastapi import APIRouter
from app.core.config import APP_NAME, APP_VERSION

router = APIRouter()

@router.get("/")
def root() -> dict[str, str]:
    return {"name": APP_NAME, "message": "RIA backend is running"}

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ria-backend", "version": APP_VERSION}
