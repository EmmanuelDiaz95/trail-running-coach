from __future__ import annotations

import os
import sys
import time
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tracker.garmin_sync import _load_env

_load_env()

from dashboard.serve import (
    _auto_sync,
    DASHBOARD_DIR,
)
from api.routes_dashboard import router as dashboard_router
from api.routes_coach import router as coach_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start auto-sync background thread on startup."""
    sync_thread = threading.Thread(target=_auto_sync, daemon=True)
    sync_thread.start()
    print("[lifespan] Auto-sync thread started")
    yield
    print("[lifespan] Shutting down")


app = FastAPI(title="Tarahumara Ultra Tracker", lifespan=lifespan)

# API routes (must be registered BEFORE static files mount)
app.include_router(dashboard_router)
app.include_router(coach_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Static files — serves dashboard.html at root
# This MUST be last because it catches all unmatched routes
app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="static")
