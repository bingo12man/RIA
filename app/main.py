
from fastapi import FastAPI

from app.api.routes import router
from app.api.stream_routes import router as stream_router
from app.core.config import APP_NAME, APP_VERSION


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url=None,
    redoc_url=None
)

app.include_router(router)
app.include_router(stream_router)
