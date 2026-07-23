"""
RogueAI FastAPI backend.

Ideal backend structure when you are ready to split this single file:

backend/
  app/
    main.py                 # FastAPI app factory and route registration
    core/
      config.py             # Environment-driven settings
      logging.py            # Logging configuration
    api/
      routes/
        health.py           # Health endpoints
        research.py         # Research endpoints
    models/
      research.py           # Pydantic request/response models
    services/
      research_service.py   # Executor + pipeline orchestration
    utils/
      text.py               # clean_report_text, extract_sources, extract_verdict
  requirements.txt
  render.yaml

This project currently keeps everything in main.py because requested, but the
sections below mirror that production structure so the code can be split later
without changing endpoint behavior.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from pipeline import run_research_pipeline


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()


class Settings:
    """Environment-based application settings.

    API keys are intentionally read from .env / Render environment variables.
    They must never be hardcoded in the application source.
    """

    app_name: str = os.getenv("APP_NAME", "RogueAI")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")
    environment: str = os.getenv("ENVIRONMENT", "development")
    allowed_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5500,http://127.0.0.1:8000,http://localhost:5500",
        ).split(",")
        if origin.strip()
    ]
    max_workers: int = int(os.getenv("RESEARCH_MAX_WORKERS", "4"))
    request_timeout_seconds: int = int(os.getenv("RESEARCH_TIMEOUT_SECONDS", "180"))


settings = Settings()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("rogueai.api")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ResearchRequest(BaseModel):
    """Client payload for starting a deep research run."""

    topic: str = Field(
        ...,
        min_length=3,
        max_length=300,
        description="The research topic or question.",
        examples=["Recent advances in AI-powered drug discovery"],
    )

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("Topic cannot be empty.")
        if len(cleaned) < 3:
            raise ValueError("Topic must contain at least 3 characters.")
        return cleaned


class Source(BaseModel):
    """A source discovered from search results, scraped content, or report text."""

    title: str | None = None
    url: str


class ResearchResponse(BaseModel):
    """Structured response returned by /api/research."""

    status: str = "success"
    topic: str
    report: str
    feedback: str | None = None
    verdict: str | None = None
    sources: list[Source] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Consistent error response shape for frontend clients."""

    status: str = "error"
    detail: str


class HealthResponse(BaseModel):
    """Health check response for Render and uptime monitors."""

    status: str
    service: str
    version: str
    environment: str


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

URL_PATTERN = re.compile(r"https?://[^\s\])}>\"']+", re.IGNORECASE)


def stringify(value: Any) -> str:
    """Convert LangChain outputs and regular Python values into clean text."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "content"):
        return str(value.content)
    return str(value)


def clean_report_text(report: Any) -> str:
    """Normalize report text for API clients without changing its meaning."""

    text = stringify(report)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip()


def extract_sources(*values: Any) -> list[Source]:
    """Extract unique URLs from pipeline output and return API-safe sources."""

    seen: set[str] = set()
    sources: list[Source] = []

    for value in values:
        text = stringify(value)
        for raw_url in URL_PATTERN.findall(text):
            url = raw_url.rstrip(".,;:")
            if url in seen:
                continue
            seen.add(url)
            sources.append(Source(url=url))

    return sources


def extract_verdict(feedback: Any) -> str | None:
    """Extract a compact critic verdict when the feedback contains one."""

    text = stringify(feedback).strip()
    if not text:
        return None

    verdict_match = re.search(
        r"(?:verdict|overall)\s*[:\-]\s*(.+)",
        text,
        flags=re.IGNORECASE,
    )
    if verdict_match:
        return verdict_match.group(1).splitlines()[0].strip()

    first_line = text.splitlines()[0].strip()
    return first_line[:180] if first_line else None


def normalize_pipeline_result(topic: str, result: dict[str, Any]) -> ResearchResponse:
    """Map the AI pipeline dictionary into the public API response contract."""

    report = clean_report_text(result.get("report"))
    feedback = clean_report_text(result.get("feedback"))
    search_output = result.get("search_results") or result.get("search_result")
    scraped_content = result.get("scraped_content")

    if not report:
        raise ValueError("Research pipeline completed but returned an empty report.")

    return ResearchResponse(
        topic=topic,
        report=report,
        feedback=feedback or None,
        verdict=extract_verdict(feedback),
        sources=extract_sources(search_output, scraped_content, report),
    )


# ---------------------------------------------------------------------------
# Application Lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared resources once and clean them up on shutdown."""

    app.state.executor = ThreadPoolExecutor(max_workers=settings.max_workers)
    logger.info("RogueAI backend started with %s worker threads", settings.max_workers)
    try:
        yield
    finally:
        app.state.executor.shutdown(wait=False, cancel_futures=True)
        logger.info("RogueAI backend shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Production-ready API backend for the RogueAI deep research application.",
    lifespan=lifespan,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
    },
)


# CORS is restricted to known frontend origins. On Render/Vercel, set
# CORS_ALLOWED_ORIGINS to your deployed frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)


# ---------------------------------------------------------------------------
# Exception Handling
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log full tracebacks while returning a safe message to the frontend."""

    logger.error(
        "Unhandled error while processing %s %s\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(detail="Internal server error while running research.").model_dump(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> dict[str, str]:
    """Small root endpoint for humans opening the backend URL."""

    return {
        "status": "ok",
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health endpoint suitable for Render checks and monitoring."""

    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@app.post("/api/research", response_model=ResearchResponse)
async def research(request: ResearchRequest, http_request: Request) -> ResearchResponse:
    """Run the blocking AI research pipeline without blocking FastAPI's event loop."""

    loop = asyncio.get_running_loop()

    try:
        raw_result = await asyncio.wait_for(
            loop.run_in_executor(
                http_request.app.state.executor,
                run_research_pipeline,
                request.topic,
            ),
            timeout=settings.request_timeout_seconds,
        )

        if not isinstance(raw_result, dict):
            raise ValueError("Research pipeline returned an invalid response type.")

        return normalize_pipeline_result(topic=request.topic, result=raw_result)

    except asyncio.TimeoutError as exc:
        logger.warning("Research timed out for topic=%r", request.topic)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Research request timed out. Try a narrower topic or increase the timeout.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Research failed for topic=%r\n%s",
            request.topic,
            traceback.format_exc(),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete research pipeline.",
        ) from exc


# Render runs web services using a start command such as:
# uvicorn main:app --host 0.0.0.0 --port $PORT
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=settings.environment == "development",
    )
