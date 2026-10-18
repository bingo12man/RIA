import importlib
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ria1.scripts.module5_conversation_api import app as conversation_app

app = FastAPI(
    title="RIA-1 Integrated Backend",
    version="5.7",
)

MAIN_MODULE = os.getenv("RIA_MAIN_MODULE", "app.main")
MAIN_ATTRIBUTE = os.getenv("RIA_MAIN_ATTRIBUTE", "app")


@app.get("/integration/health")
def integration_health():
    return {
        "status": "ok",
        "module": "5.7",
        "conversation": "/conversation",
        "original_backend": "/original",
    }


# Preserve the working Module 5.6 application.
app.mount("/conversation", conversation_app)

# Import and mount the existing RIA backend.
try:
    module = importlib.import_module(MAIN_MODULE)
    original_app = getattr(module, MAIN_ATTRIBUTE)

    if original_app is app:
        raise RuntimeError("Cannot mount application into itself")

    app.mount("/original", original_app)

except (ImportError, AttributeError) as error:
    # Fail explicitly rather than pretending the old backend works.
    raise RuntimeError(
        f"Cannot load original RIA application: "
        f"{MAIN_MODULE}.{MAIN_ATTRIBUTE}. "
        f"Check the module path before starting."
    ) from error
