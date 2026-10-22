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
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .predict import MAX_TEXT_LENGTH, TicketPredictor

logger = logging.getLogger(__name__)


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_TEXT_LENGTH)]
    mode: Literal["word", "semantic"] = "word"
    check_multiple_requests: Annotated[bool, Field(strict=True)] = False

    @model_validator(mode="after")
    def check_semantic_option(self):
        if self.check_multiple_requests and self.mode != "semantic":
            raise ValueError("The separate-request check is available only in semantic mode.")
        return self

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
    model_mode: Literal["word", "semantic"] = "word"
    model_name: str = "Word baseline"
    scope_score: Annotated[float, Field(ge=0, le=1)] | None = None
    scope_threshold: Annotated[float, Field(gt=0, le=1)] | None = None
    input_truncated: bool = False
    multiple_request_check_enabled: bool = False
    multiple_requests_detected: bool = False
    request_check_status: str | None = None
    request_check_version: int | None = None


def create_app(model_dir: Path | None = None, semantic_model_dir: Path | None = None, requests_db: Path | None = None) -> FastAPI:
    """Load one trusted bundle per worker at startup, not per request."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.request_store = None
        database = requests_db if requests_db is not None else os.environ.get("SUPPORT_TICKET_REQUESTS_DB")
        if database:
            try:
                from .request_store import RequestStore
                application.state.request_store = RequestStore(Path(database))
            except Exception as error:
                logger.error("Request storage initialization failed (%s)", type(error).__name__)
        application.state.predictor = None
        application.state.semantic_predictor = None
        configured = model_dir if model_dir is not None else os.environ.get("SUPPORT_TICKET_MODEL_DIR")
        if configured:
            try:
                application.state.predictor = TicketPredictor(Path(configured))
            except Exception as error:
                # Keep paths and bundle details out of HTTP responses and logs.
                logger.error("Model initialization failed (%s)", type(error).__name__)
        semantic_configured = (semantic_model_dir if semantic_model_dir is not None else
                               os.environ.get("SUPPORT_TICKET_SEMANTIC_MODEL_DIR"))
        if semantic_configured:
            try:
                from .semantic_bundle import SemanticPredictor
                application.state.semantic_predictor = SemanticPredictor(Path(semantic_configured))
            except Exception as error:
                logger.error("Semantic initialization failed (%s)", type(error).__name__)
        yield
        application.state.request_store = None
        application.state.predictor = None
        application.state.semantic_predictor = None

    application = FastAPI(
        title="Support Ticket AI",
        version="0.5.0",
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

    def predictor_or_unavailable(mode="word"):
        attribute = "predictor" if mode == "word" else "semantic_predictor"
        predictor = getattr(application.state, attribute, None)
        if predictor is None:
            raise HTTPException(status_code=503, detail="Model is not ready.")
        return predictor

    @application.get("/healthz")
    def health():
        return {"status": "alive"}

    @application.get("/models")
    def models():
        return {"default": "word", "modes": [
            {"mode": "word", "name": "Word baseline", "available": getattr(application.state, "predictor", None) is not None},
            {"mode": "semantic", "name": "Semantic encoder + scope gate (experimental)",
             "supports_multiple_request_check": True,
             "available": getattr(application.state, "semantic_predictor", None) is not None},
        ]}

    @application.get("/readyz")
    def readiness(mode: Literal["word", "semantic"] = "word"):
        predictor = predictor_or_unavailable(mode)
        return {"status": "ready", "model_sha256": predictor.metadata["model_sha256"], "model_mode": mode}

    @application.post("/predict", response_model=PredictionResponse)
    def predict(body: PredictionRequest):
        predictor = predictor_or_unavailable(body.mode)
        try:
            if body.check_multiple_requests:
                from .multi_intent import VERSION, guarded_prediction
                outcomes = guarded_prediction(body.text, predictor)
                inspection = outcomes["inspection"]
                result = {**outcomes["guarded"], "multiple_request_check_enabled": True,
                          "multiple_requests_detected": inspection["review_triggered"],
                          "request_check_status": inspection["status"], "request_check_version": VERSION}
            else:
                result = predictor.predict(body.text)
            return {**result, "model_mode": body.mode, "model_name": "Word baseline" if body.mode == "word" else "Semantic encoder + scope gate (experimental)"}
        except Exception as error:
            logger.error("Prediction failed (%s)", type(error).__name__)
            raise HTTPException(status_code=500, detail="Prediction could not be completed.") from error

    from .request_api import register_request_routes
    register_request_routes(application, predict, PredictionRequest, PredictionResponse)
    return application


app = create_app()
