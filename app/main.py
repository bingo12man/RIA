from fastapi import FastAPI
from app.api.routes import router
from app.core.config import APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION, docs_url=None, redoc_url=None)
app.include_router(router)
