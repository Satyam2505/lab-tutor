"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.answer_gate import assert_gate_invariant
from backend.api import ROUTERS
from backend.config import get_settings
from backend.db import create_all, dispose_engine
from backend.tier1_compute.experiments import all_plugins, ready_plugins

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("labtutor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Fail fast if the answer-gate guarantee has been weakened. Better to
    # refuse to start than to serve students with a gate that no longer
    # holds.
    assert_gate_invariant()

    if settings.env == "production" and settings.session_secret == "dev-insecure-secret":
        raise RuntimeError(
            "LABTUTOR_SESSION_SECRET is still the development default. "
            "Generate one with: openssl rand -hex 32"
        )

    await create_all()

    total = len(all_plugins())
    ready = len(ready_plugins())
    log.info(
        "LabTutor starting: %d experiments registered, %d ready, LLM backend=%s",
        total, ready, settings.llm_backend,
    )
    if ready < total:
        log.warning(
            "%d experiment(s) are not usable yet -- their formulas have not been "
            "transcribed from the IACHY102 manual. Submissions against them will "
            "escalate to review rather than produce a diagnosis.",
            total - ready,
        )

    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="LabTutor",
        description=(
            "Chemistry lab learning support for IACHY102. Diagnosis is "
            "deterministic; language models only phrase what has already been "
            "decided."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    for router in ROUTERS:
        app.include_router(router)
    return app


app = create_app()
