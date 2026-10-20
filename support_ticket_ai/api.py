"""Local FastAPI service for reviewed category suggestions."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .predict import MAX_TEXT_LENGTH, TicketPredictor

logger = logging.getLogger(__name__)


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_TEXT_LENGTH)]

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ticket text cannot be blank.")
        return value.strip()


class PredictionResponse(BaseModel):
    suggested_category: str | None
    model_top_category: str
    decision: Literal["suggestion", "abstain"]
    abstention_threshold: Annotated[float, Field(gt=0, le=1)] | None
    uncalibrated_probability: Annotated[float, Field(ge=0, le=1)]
    requires_human_review: Literal[True]
    review_reason: str
    model_sha256: str


def create_app(model_dir: Path | None = None) -> FastAPI:
    """Load one trusted bundle per worker at startup, not per request."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.predictor = None
        configured = model_dir if model_dir is not None else os.environ.get("SUPPORT_TICKET_MODEL_DIR")
        if configured:
            try:
                application.state.predictor = TicketPredictor(Path(configured))
            except Exception as error:
                # Keep paths and bundle details out of HTTP responses and logs.
                logger.error("Model initialization failed (%s)", type(error).__name__)
        yield
        application.state.predictor = None

    application = FastAPI(
        title="Support Ticket AI",
        version="0.2.0",
        description="Category suggestions requiring human review; scores are not calibrated.",
        lifespan=lifespan,
    )
    web_directory = Path(__file__).resolve().parent / "web"
    application.mount("/assets", StaticFiles(directory=web_directory), name="assets")

    @application.get("/", include_in_schema=False)
    def workspace():
        return FileResponse(web_directory / "index.html", headers={"Cache-Control": "no-cache"})

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request, error):
        # Framework defaults can echo submitted input; return schema errors only.
        details = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                   for item in error.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    def predictor_or_unavailable() -> TicketPredictor:
        predictor = getattr(application.state, "predictor", None)
        if predictor is None:
            raise HTTPException(status_code=503, detail="Model is not ready.")
        return predictor

    @application.get("/healthz")
    def health():
        return {"status": "alive"}

    @application.get("/readyz")
    def readiness():
        predictor = predictor_or_unavailable()
        return {"status": "ready", "model_sha256": predictor.metadata["model_sha256"]}

    @application.post("/predict", response_model=PredictionResponse)
    def predict(body: PredictionRequest):
        predictor = predictor_or_unavailable()
        try:
            return predictor.predict(body.text)
        except Exception as error:
            logger.error("Prediction failed (%s)", type(error).__name__)
            raise HTTPException(status_code=500, detail="Prediction could not be completed.") from error

    return application


app = create_app()
