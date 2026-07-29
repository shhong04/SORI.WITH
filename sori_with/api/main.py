from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sori_with import __version__
from sori_with.api.routes.sessions import router as sessions_router
from sori_with.api.routes.practice import router as practice_router
from sori_with.api.routes.rooms import router as rooms_router
from sori_with.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "SORI.WITH AI Ensemble Platform backend "
        "(Phase1 Analysis + Phase2 Practice/Sessionist + Phase3 Ensemble Room/Render)"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router, prefix=settings.api_prefix)
app.include_router(practice_router, prefix=settings.api_prefix)
app.include_router(rooms_router, prefix=settings.api_prefix)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "app": settings.app_name}
